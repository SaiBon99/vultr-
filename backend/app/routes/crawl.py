"""POST /crawl. Reviewer token only. Never touches /proxy/memory/*, the gate or quarantine."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.crawl.service import crawl
from app.deps import ReviewerAuth
from app.models import CrawlRequest, CrawlResult, Error

router = APIRouter(tags=["crawl"])


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
    )
    out = result.model_dump()
    # CrawlUsage properties are optional, not nullable: drop the counts the model did not report.
    out["usage"] = result.usage.model_dump(exclude_none=True) if result.usage else None
    return JSONResponse(out)
