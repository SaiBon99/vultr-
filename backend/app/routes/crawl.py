"""POST /crawl and its run logs. Reviewer token only.

After a successful run the summary goes through the memory gate (app.memory_store) in a new
tainted session; that save never changes the response.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import gate, memory_store
from app.crawl.service import crawl
from app.deps import ApiError, ReviewerAuth
from app.models import CrawlRequest, CrawlResult, Error
from app.runlog import CONTENT_TYPE, run_log_key

router = APIRouter(tags=["crawl"])
log = logging.getLogger("app.crawl")


@router.post(
    "/crawl",
    operation_id="crawlPage",
    dependencies=[ReviewerAuth],
    response_model=CrawlResult,
    responses={code: {"model": Error} for code in (401, 422, 502, 503, 504)},
)
async def crawl_page(body: CrawlRequest, request: Request) -> JSONResponse:
    state = request.app.state
    result = await crawl(
        body.url,
        settings=state.settings,
        guard=state.crawl_guard,
        runner=state.crawl_runner,
        slots=state.crawl_slots,
        store=state.store,
    )
    await _save_to_memory(state, result)
    out = result.model_dump(mode="json")
    # CrawlUsage properties are optional, not nullable: drop the counts the model did not report.
    out["usage"] = result.usage.model_dump(exclude_none=True) if result.usage else None
    return JSONResponse(out)


async def _save_to_memory(state, result: CrawlResult) -> None:
    """No database configured (tests, local UI): skip. A failed save stores nothing and does not
    change the crawl response; it is logged. shortcut: surface save status in the response once
    the contract allows it."""
    if state.db.proxy is None:
        return
    allowlist = gate.normalize_allowlist(state.settings.egress_allowlist)
    try:
        async with state.db.proxy.connection() as conn:
            saved = await memory_store.save_crawl(conn, result, allowlist)
    except Exception:
        log.exception("crawl memory save failed url=%s", result.final_url[:300])
        return
    for s in saved:
        log.info(
            "crawl memory saved table=%s verdict=%s risk=%s id=%s",
            s["table"],
            s["verdict"],
            s["risk_score"],
            s["id"],
        )


@router.get(
    "/crawl/runs/{run_id}/log",
    operation_id="getCrawlRunLog",
    dependencies=[ReviewerAuth],
    response_class=Response,
    responses={
        200: {"content": {CONTENT_TYPE: {"schema": {"type": "string"}}}},
        **{code: {"model": Error} for code in (401, 404, 503)},
    },
)
async def get_crawl_run_log(run_id: UUID, request: Request) -> Response:
    store = request.app.state.store
    if store is None:
        raise ApiError(503, "Object storage is not configured", "storage_missing")
    try:
        body = await run_in_threadpool(store.get, run_log_key("crawl", str(run_id)))
    except Exception as exc:
        raise ApiError(503, "Object storage is unreachable", "storage_unavailable") from exc
    if body is None:
        raise ApiError(404, "Run log not found", "not_found")
    return Response(body, media_type=CONTENT_TYPE)
