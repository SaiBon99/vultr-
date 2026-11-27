"""HTTP surface for the memory quarantine.

Sandbox-facing (session_id is the only credential the sandbox holds):
- POST /proxy/read               external read, taints the session
- POST /proxy/memory/write       memory write; 201 when active, 202 when quarantined
- GET  /proxy/memory/active      active rows in the session's namespace only

Reviewer and demo. Every route here needs REVIEW_TOKEN, passed as ?token= or the X-Review-Token header:
- GET  /ui                       quarantine review page
- POST /ui/rows/{id}/purge
- POST /ui/rows/{id}/override    form field: reason
- GET  /audit                    hash-chained audit events
- GET  /demo/runs                saved demo results
- POST /demo/runs                start naive and gated runs in the background (one at a time)
"""

import asyncio
import html

import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from ..config import load_settings
from .app import get_memory
from .service import ReviewError

router = APIRouter()
_background: set[asyncio.Task] = set()


class ReadRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    ref: str = Field(min_length=1, max_length=120)


class WriteRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=2000)


@router.post("/proxy/read")
async def proxy_read(body: ReadRequest) -> dict:
    memory = await get_memory()
    try:
        return await memory.read(body.session_id, body.ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proxy/memory/write")
async def proxy_write(body: WriteRequest, response: Response) -> dict:
    memory = await get_memory()
    try:
        result = await memory.write(body.session_id, body.content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response.status_code = 201 if result.status == "active" else 202
    return {"status": result.status, "verdict": result.verdict, "flags": result.flags, "row_id": result.row_id}


@router.get("/proxy/memory/active")
async def proxy_active(session_id: str) -> list[dict]:
    memory = await get_memory()
    try:
        return await memory.recall_for(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_reviewer(token: str | None, header_token: str | None) -> str:
    expected = load_settings().review_token
    if not expected:
        raise HTTPException(status_code=503, detail="REVIEW_TOKEN is not set; reviewer routes are disabled")
    supplied = token or header_token or ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="reviewer token required")
    return supplied


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _render_queue(rows: list[dict], token: str) -> str:
    if not rows:
        return "<p>Nothing is waiting for review.</p>"
    sessions: dict[str, list[dict]] = {}
    for row in rows:
        sessions.setdefault(row["session_id"], []).append(row)
    parts = []
    for session_id, items in sessions.items():
        parts.append(f"<h2>Session {_esc(session_id)}</h2>")
        for row in items:
            note = row.get("judge_note") or {}
            needs_reason = row["verdict"] == "POLICY_BLOCKED"
            parts.append(
                "<div class='row'>"
                f"<p><strong>#{_esc(row['id'])}</strong> verdict <code>{_esc(row['verdict'])}</code> "
                f"flags <code>{_esc(', '.join(row['flags']))}</code></p>"
                f"<blockquote>{_esc(row['content'])}</blockquote>"
                f"<p>Judge: {_esc(note.get('summary', note.get('error', 'not run')))} "
                f"(risk {_esc(note.get('risk_level', '-'))}, suggests {_esc(note.get('recommended_action', '-'))})</p>"
                f"<form method='post' action='/ui/rows/{_esc(row['id'])}/purge?{_esc(urlencode({'token': token}))}' style='display:inline'>"
                "<button>Purge</button></form> "
                f"<form method='post' action='/ui/rows/{_esc(row['id'])}/override?{_esc(urlencode({'token': token}))}' style='display:inline'>"
                f"<input name='reason' placeholder='{'typed reason required' if needs_reason else 'optional reason'}' size='40'>"
                "<button>Override</button></form>"
                "</div>"
            )
    return "".join(parts)


@router.get("/ui", response_class=HTMLResponse)
async def review_ui(token: str | None = Query(None), x_review_token: str | None = Header(None)) -> str:
    token = _require_reviewer(token, x_review_token)
    memory = await get_memory()
    rows = await memory.review_queue()
    return (
        "<!doctype html><meta charset='utf-8'><title>Quarantine review</title>"
        "<style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}"
        ".row{border:1px solid #ccc;border-radius:6px;padding:.75rem;margin:.75rem 0}"
        "blockquote{background:#f6f6f6;margin:.5rem 0;padding:.5rem;white-space:pre-wrap}</style>"
        "<h1>Quarantine review</h1>"
        "<p>Frozen writes wait here. Purge removes the content and blocks similar future writes. "
        "Override moves the row into active memory.</p>"
        f"{_render_queue(rows, token)}"
    )


@router.post("/ui/rows/{row_id}/purge")
async def ui_purge(
    row_id: int, token: str | None = Query(None), x_review_token: str | None = Header(None)
) -> RedirectResponse:
    token = _require_reviewer(token, x_review_token)
    memory = await get_memory()
    try:
        await memory.purge(row_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/ui?{urlencode({'token': token})}", status_code=303)


@router.post("/ui/rows/{row_id}/override")
async def ui_override(
    row_id: int,
    reason: str = Form(""),
    token: str | None = Query(None),
    x_review_token: str | None = Header(None),
) -> RedirectResponse:
    token = _require_reviewer(token, x_review_token)
    memory = await get_memory()
    try:
        await memory.override(row_id, reason or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/ui?{urlencode({'token': token})}", status_code=303)


@router.get("/audit")
async def audit(token: str | None = Query(None), x_review_token: str | None = Header(None)) -> list[dict]:
    _require_reviewer(token, x_review_token)
    memory = await get_memory()
    rows = await memory.store.list_audit()
    return [
        {**r, "created_at": r["created_at"].isoformat() if r.get("created_at") else None} for r in rows
    ]


@router.get("/demo/runs")
async def demo_runs(token: str | None = Query(None), x_review_token: str | None = Header(None)) -> list[dict]:
    _require_reviewer(token, x_review_token)
    memory = await get_memory()
    rows = await memory.store.list_demo_runs()
    return [
        {**r, "created_at": r["created_at"].isoformat() if r.get("created_at") else None} for r in rows
    ]


@router.post("/demo/runs", status_code=202)
async def start_demo(token: str | None = Query(None), x_review_token: str | None = Header(None)) -> dict:
    from .demo import run_demo_pair  # imported here to keep the router import light

    _require_reviewer(token, x_review_token)
    if _background:
        raise HTTPException(status_code=409, detail="a demo is already running")
    memory = await get_memory()
    settings = load_settings()
    task = asyncio.create_task(run_demo_pair(memory, settings))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"started": True, "note": "poll GET /demo/runs; each mode is saved when it finishes"}
