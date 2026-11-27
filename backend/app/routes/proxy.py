"""Host and sandbox endpoints. DB-backed handlers are Phase 1; auth and validation are live."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import ApiError, HostAuth, SessionAuth, SettingsDep, optional_reviewer_ok
from app.models import (
    ActiveMemories,
    CreateSessionRequest,
    CreateSessionResponse,
    Error,
    MemoryWriteAccepted,
    MemoryWriteQuarantined,
    MemoryWriteRequest,
    ProxyReadRequest,
    ProxyReadResponse,
)

router = APIRouter(prefix="/proxy", tags=["proxy"])


def not_implemented() -> ApiError:
    return ApiError(501, "not implemented: Phase 1", "not_implemented")


@router.post(
    "/sessions",
    operation_id="createSession",
    status_code=201,
    response_model=CreateSessionResponse,
    dependencies=[HostAuth],
    responses={401: {"model": Error}, 403: {"model": Error}},
)
async def create_session(
    settings: SettingsDep,
    reviewer_ok: Annotated[bool, Depends(optional_reviewer_ok)],
    body: CreateSessionRequest | None = None,
) -> CreateSessionResponse:
    if (
        body is not None
        and body.gate_mode == "naive"
        and not (settings.DEMO_ALLOW_NAIVE and reviewer_ok)
    ):
        raise ApiError(403, "gate_mode=naive is disabled", "naive_disabled")
    raise not_implemented()


@router.post(
    "/read",
    operation_id="proxyRead",
    response_model=ProxyReadResponse,
    responses={401: {"model": Error}, 422: {"model": Error}},
)
async def proxy_read(token: SessionAuth, body: ProxyReadRequest) -> ProxyReadResponse:
    raise not_implemented()


@router.post(
    "/memory/write",
    operation_id="proxyMemoryWrite",
    status_code=201,
    response_model=MemoryWriteAccepted,
    responses={
        202: {"model": MemoryWriteQuarantined, "description": "Frozen in quarantine_queue"},
        401: {"model": Error},
        422: {"model": Error},
    },
)
async def proxy_memory_write(
    token: SessionAuth, body: MemoryWriteRequest
) -> MemoryWriteAccepted | MemoryWriteQuarantined:
    raise not_implemented()


@router.get(
    "/memory/active",
    operation_id="proxyMemoryActive",
    response_model=ActiveMemories,
    responses={401: {"model": Error}},
)
async def proxy_memory_active(
    token: SessionAuth,
    q: Annotated[str | None, Query(max_length=2000)] = None,
    k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ActiveMemories:
    raise not_implemented()
