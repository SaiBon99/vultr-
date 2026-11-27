"""Unauthenticated endpoints: /health and /keys/public."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.deps import ApiError
from app.models import Error, Health, HealthChecks, PublicKey

router = APIRouter(tags=["public"])


async def _db_check(request: Request) -> str:
    db = request.app.state.db
    if not db.configured:
        return "skipped"
    return "ok" if await db.ping() else "error"


async def _storage_check(request: Request) -> str:
    store = request.app.state.store
    if store is None:
        return "skipped"
    return "ok" if await run_in_threadpool(store.ping) else "error"


async def _inference_check(request: Request) -> str:
    judge = request.app.state.judge
    ping = getattr(judge, "ping", None)
    if judge is None or ping is None:
        return "skipped"
    return "ok" if await ping() else "error"


@router.get("/health", operation_id="getHealth", response_model=Health)
async def get_health(request: Request) -> Health:
    checks = HealthChecks(
        db=await _db_check(request),
        object_storage=await _storage_check(request),
        inference=await _inference_check(request),
    )
    degraded = "error" in checks.model_dump().values()
    return Health(status="degraded" if degraded else "ok", checks=checks)


@router.get(
    "/keys/public",
    operation_id="getPublicKey",
    response_model=PublicKey,
    responses={503: {"model": Error}},
)
async def get_public_key(request: Request) -> PublicKey:
    signer = request.app.state.signer
    if signer is None:
        raise ApiError(503, "Receipt signing key is not configured", "signing_key_missing")
    return PublicKey.model_validate(signer.public_key_doc())
