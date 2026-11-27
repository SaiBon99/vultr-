"""POST /crawl. Reviewer token only. After a successful run the summary goes through the memory
gate (app.memory_store) in a new tainted session; frozen rows are then explained by the isolated
judge in the background. The response shape is unchanged."""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app import gate, memory_store
from app.crawl.service import crawl
from app.deps import ReviewerAuth
from app.judge import run_judge
from app.models import CrawlRequest, CrawlResult, Error

router = APIRouter(tags=["crawl"])
log = logging.getLogger("app.crawl")


@router.post(
    "/crawl",
    operation_id="crawlPage",
    dependencies=[ReviewerAuth],
    response_model=CrawlResult,
    responses={code: {"model": Error} for code in (401, 422, 502, 503, 504)},
)
async def crawl_page(
    body: CrawlRequest, request: Request, background: BackgroundTasks
) -> JSONResponse:
    state = request.app.state
    result = await crawl(
        body.url,
        settings=state.settings,
        guard=state.crawl_guard,
        runner=state.crawl_runner,
        slots=state.crawl_slots,
    )
    saved = await _save_to_memory(state, result)
    frozen = [s for s in saved if s["table"] == "quarantine_queue"]
    if frozen and state.judge is not None:
        # After the response: a slow judge never delays the crawl, and rows read "pending" meanwhile.
        background.add_task(_judge_frozen, state, frozen, result.final_url)
    out = result.model_dump()
    # CrawlUsage properties are optional, not nullable: drop the counts the model did not report.
    out["usage"] = result.usage.model_dump(exclude_none=True) if result.usage else None
    return JSONResponse(out)


async def _save_to_memory(state, result: CrawlResult) -> list[dict[str, Any]]:
    """No database configured (tests, local UI): skip. A failed save stores nothing and does not
    change the crawl response; it is logged. shortcut: surface save status in the response once
    the contract allows it."""
    if state.db.proxy is None:
        return []
    allowlist = gate.normalize_allowlist(state.settings.egress_allowlist)
    try:
        async with state.db.proxy.connection() as conn:
            saved = await memory_store.save_crawl(conn, result, allowlist)
    except Exception:
        log.exception("crawl memory save failed url=%s", result.final_url[:300])
        return []
    for s in saved:
        log.info(
            "crawl memory saved table=%s verdict=%s risk=%s id=%s",
            s["table"], s["verdict"], s["risk_score"], s["id"],
        )
    return saved


async def _judge_frozen(state, frozen: list[dict[str, Any]], source_ref: str) -> None:
    """The judge sees only the frozen note, its rule flags and where it came from (never the
    session). run_judge never raises; a failure is stored as judge_failed (fail closed)."""
    for row in frozen:
        result = await run_judge(
            state.judge,
            content=row["content"],
            rule_flags=row["rule_flags"],
            source_snippet=f"Crawled page: {source_ref}",
        )
        try:
            async with state.db.proxy.connection() as conn:
                status = await memory_store.record_judgement(conn, row["id"], result)
        except Exception:
            log.exception("crawl judge save failed id=%s", row["id"])
            continue
        log.info("crawl judge id=%s status=%s", row["id"], status)
