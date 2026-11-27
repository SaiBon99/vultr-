"""Audit log and receipt retrieval (reviewer only)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.deps import ApiError, ReviewerAuth
from app.models import AuditLog, Error, Receipt
from app.receipts import receipt_object_key
from app.routes.proxy import not_implemented

router = APIRouter(tags=["review"], dependencies=[ReviewerAuth])


@router.get(
    "/audit",
    operation_id="getAudit",
    response_model=AuditLog,
    responses={401: {"model": Error}},
)
async def get_audit(session_id: Annotated[UUID | None, Query()] = None) -> AuditLog:
    raise not_implemented()


@router.get(
    "/receipts/{id}",
    operation_id="getReceipt",
    response_model=Receipt,
    responses={401: {"model": Error}, 404: {"model": Error}, 503: {"model": Error}},
)
async def get_receipt(id: UUID, request: Request) -> Receipt:
    store = request.app.state.store
    if store is None:
        raise ApiError(503, "Object storage is not configured", "storage_missing")
    raw = await run_in_threadpool(store.get, receipt_object_key(str(id)))
    if raw is None:
        raise ApiError(404, "Receipt not found", "not_found")
    return Receipt.model_validate_json(raw)
