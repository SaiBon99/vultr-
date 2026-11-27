"""Review UI endpoints for the quarantine queue."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.deps import ReviewerAuth
from app.models import DecideRequest, DecideResponse, Error, QuarantineList, QuarantineStatus
from app.routes.proxy import not_implemented

router = APIRouter(prefix="/quarantine", tags=["review"], dependencies=[ReviewerAuth])


@router.get(
    "",
    operation_id="listQuarantine",
    response_model=QuarantineList,
    responses={401: {"model": Error}},
)
async def list_quarantine(
    status: Annotated[QuarantineStatus | None, Query()] = None,
) -> QuarantineList:
    raise not_implemented()


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
