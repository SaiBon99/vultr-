"""Host-side tool executors for the chat agent.

Each executor takes args the model asked for (already validated by app.chat.model) and returns a
ToolOutcome. The host writes every step summary; the model never does. Nothing here buys or sends
anything: place_order is always simulated and send_email is always refused.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.chat.memory import ChatMemory
from app.chat.state import ChatState
from app.config import Settings
from app.crawl.errors import CrawlError
from app.crawl.fetch import Page, fetch_page
from app.crawl.guard import PublicTargetGuard, UnsafeTarget

log = logging.getLogger("app.chat")

ORDER_ID_CHARS = string.ascii_uppercase + string.digits
SUMMARY_MAX = 300


@dataclass
class ToolOutcome:
    status: str  # ok | refused | error
    error_code: str | None
    summary: str
    detail: dict[str, Any] | None  # the contract's ChatStepEvent.detail
    observation: dict[str, Any]  # what the model is told; never contains page text
    page: Page | None = None  # browse only: the fetched page, parsed inside the sandbox


@dataclass(frozen=True)
class ToolContext:
    settings: Settings
    guard: PublicTargetGuard
    memory: ChatMemory
    state: ChatState


async def execute(ctx: ToolContext, tool: str, args: dict[str, Any]) -> ToolOutcome:
    return await _EXECUTORS[tool](ctx, args)


async def browse(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    url = args["url"].strip()
    try:
        target = await ctx.guard.check(url)
    except UnsafeTarget as exc:
        return _browse_failed(ctx, url, "refused", "unsafe_target", f"Refused {_shown(url)}: {exc}")
    try:
        page = await fetch_page(target, ctx.guard, ctx.settings.CRAWL_MAX_BYTES)
    except CrawlError as exc:
        return _browse_failed(
            ctx,
            url,
            "error",
            exc.code or "fetch_failed",
            f"Could not read {_shown(url)}: {exc.detail}",
        )
    try:
        # The session is tainted before the model or the agent sees a byte of the page.
        await ctx.memory.mark_tainted(ctx.state.session_id, page.final_url)
    except Exception:
        log.exception("chat taint failed chat_id=%s", ctx.state.chat_id)
        return _browse_failed(
            ctx, url, "error", "memory_unavailable", "The page was not used: memory is unavailable"
        )
    ctx.state.tainted = True
    return ToolOutcome(
        status="ok",
        error_code=None,
        summary=f"Read {_shown(page.final_url)} ({_size(page.size)}); session is now tainted",
        detail={
            "kind": "browse",
            "url": url,
            "final_url": page.final_url[:2048],
            "title": None,  # filled in once the sandbox has parsed the page
            "bytes": page.size,
            "session_tainted": True,
        },
        observation={},
        page=page,
    )


def _browse_failed(ctx: ToolContext, url: str, status: str, code: str, summary: str) -> ToolOutcome:
    return ToolOutcome(
        status=status,
        error_code=code,
        summary=summary[:SUMMARY_MAX],
        detail={
            "kind": "browse",
            "url": url[:2048],
            "final_url": None,
            "title": None,
            "bytes": None,
            "session_tainted": ctx.state.tainted,
        },
        observation={"status": status, "error_code": code},
    )


async def remember(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    content = args["content"]
    try:
        saved = await ctx.memory.remember(ctx.state.session_id, content)
    except Exception:
        log.exception("chat remember failed chat_id=%s", ctx.state.chat_id)
        return _memory_unavailable("Could not save the note: memory is unavailable")
    verdict, score = saved["verdict"], saved["risk_score"]
    stored = saved["table"] == "memories"
    return ToolOutcome(
        status="ok",
        error_code=None,
        summary="Saved to memory" if stored else f"Quarantined as {verdict}, risk {score}",
        detail={
            "kind": "remember",
            "content": content,
            "verdict": verdict,
            "risk_score": score,
            "rule_flags": list(saved["rule_flags"]),
            "table": saved["table"],
            "id": str(saved["id"]),
            "payload_hash": saved["payload_hash"],
        },
        observation={"status": "ok", "saved": stored, "verdict": verdict},
    )


async def recall(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    try:
        rows = await ctx.memory.recall(ctx.state.session_id, args.get("query"))
    except Exception:
        log.exception("chat recall failed chat_id=%s", ctx.state.chat_id)
        return _memory_unavailable("Could not read memory: memory is unavailable")
    items = [{"id": str(r["id"]), "content": r["content"]} for r in rows]
    noun = "note" if len(items) == 1 else "notes"
    return ToolOutcome(
        status="ok",
        error_code=None,
        summary=f"Recalled {len(items)} {noun}",
        detail={"kind": "recall", "items": items},
        observation={"status": "ok", "notes": [i["content"] for i in items]},
    )


def _memory_unavailable(summary: str) -> ToolOutcome:
    return ToolOutcome(
        status="error",
        error_code="memory_unavailable",
        summary=summary,
        detail=None,
        observation={"status": "error", "error_code": "memory_unavailable"},
    )


async def place_order(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    item, quantity, url = args["item"].strip(), args["quantity"], args.get("url")
    order_id = "SIM-" + "".join(secrets.choice(ORDER_ID_CHARS) for _ in range(5))
    return ToolOutcome(
        status="ok",
        error_code=None,
        summary=f"Simulated order {order_id} for {quantity} x {item[:120]}",
        detail={
            "kind": "place_order",
            "item": item,
            "quantity": quantity,
            "url": url.strip()[:2048] if url else None,
            "order_id": order_id,
            "simulated": True,
        },
        observation={"status": "ok", "order_id": order_id, "simulated": True},
    )


async def send_email(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    to, subject = args["to"].strip(), args["subject"].strip()
    return ToolOutcome(
        status="refused",
        error_code="egress_refused",
        summary=f"Email to {to[:120]} refused; the sandbox has no outbound mail",
        detail={"kind": "send_email", "to": to, "subject": subject, "sent": False},
        observation={"status": "refused", "error_code": "egress_refused"},
    )


_EXECUTORS = {
    "browse": browse,
    "remember": remember,
    "recall": recall,
    "place_order": place_order,
    "send_email": send_email,
}


def _shown(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"[:120] or url[:120]


def _size(size: int) -> str:
    return f"{size / 1000:.0f} KB" if size >= 1000 else f"{size} B"
