"""Review UI endpoints for the quarantine queue."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app import memory_store, review
from app.deps import ApiError, ReviewerAuth
from app.models import DecideRequest, DecideResponse, Error, QuarantineList, QuarantineStatus
from app.routes.proxy import not_implemented

router = APIRouter(prefix="/quarantine", tags=["review"], dependencies=[ReviewerAuth])


@router.get(
    "",
    operation_id="listQuarantine",
    response_model=QuarantineList,
    responses={401: {"model": Error}, 503: {"model": Error}},
)
async def list_quarantine(
    request: Request,
    status: Annotated[QuarantineStatus | None, Query()] = None,
) -> QuarantineList:
    db = request.app.state.db
    if db.proxy is None:
        raise ApiError(503, "Database is not configured", "db_missing")
    async with db.proxy.connection() as conn:
        rows = await memory_store.list_quarantine(conn, status)
    return review.build_queue(rows)


@router.post(
    "/{id}/decide",
    operation_id="decideQuarantine",
    response_model=DecideResponse,
    responses={
        401: {"model": Error},
        404: {"model": Error},
        409: {"model": Error},
        422: {"model": Error},
    },
)
async def decide_quarantine(id: UUID, body: DecideRequest) -> DecideResponse:
    raise not_implemented()
