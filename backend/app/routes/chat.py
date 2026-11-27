"""The shopping chat agent. Reviewer token only. Per openapi.yaml: /chat/*.

Every refusal that happens before the sandbox starts is a plain JSON error. After that the route
streams ChatEvent objects as Server-Sent Events: run, step*, then reply and done, or one error.
"""

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from app.audit import format_ts
from app.chat.service import Job, launch, new_chat_state
from app.crawl.errors import CrawlError
from app.deps import ApiError, ReviewerAuth
from app.models import Error, Wire
from app.runlog import CONTENT_TYPE, run_log_key

router = APIRouter(tags=["chat"])


class ChatSession(Wire):
    chat_id: UUID
    session_id: UUID
    created_at: str


class ChatMessageRequest(Wire):
    message: str = Field(min_length=1, max_length=2000)


def _memory(request: Request):
    memory = request.app.state.chat_memory
    if memory is None or not memory.available:
        raise ApiError(503, "The database is not configured on this host", "database_missing")
    return memory


@router.post(
    "/chat/sessions",
    operation_id="createChat",
    dependencies=[ReviewerAuth],
    status_code=201,
    response_model=ChatSession,
    responses={code: {"model": Error} for code in (401, 503)},
)
async def create_chat(request: Request) -> ChatSession:
    state = request.app.state
    memory = _memory(request)
    try:
        session_id = await memory.create_session()
    except Exception as exc:
        raise ApiError(503, "The database did not answer", "database_missing") from exc
    chat = new_chat_state(uuid4(), session_id)
    state.chats.add(chat)
    return ChatSession(
        chat_id=chat.chat_id, session_id=chat.session_id, created_at=format_ts(chat.created_at)
    )


@router.post(
    "/chat/{chat_id}/messages",
    operation_id="sendChatMessage",
    dependencies=[ReviewerAuth],
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
        **{code: {"model": Error} for code in (401, 404, 409, 422, 503)},
    },
)
async def send_chat_message(
    chat_id: UUID, body: ChatMessageRequest, request: Request
) -> StreamingResponse:
    state = request.app.state
    settings = state.settings
    chat = state.chats.get(chat_id)
    if chat is None:
        raise ApiError(404, "Unknown chat", "chat_not_found")
    if not settings.VULTR_INFERENCE_API_KEY.get_secret_value():
        raise ApiError(503, "Inference is not configured on this host", "inference_not_configured")
    memory = _memory(request)
    if chat.busy:
        raise ApiError(409, "This chat already has a message running", "chat_busy")
    try:
        state.crawl_slots.take()  # shared with /crawl: at most 2 sandbox runs together (D8)
    except CrawlError as exc:
        raise ApiError(503, "2 sandbox runs are already in progress", exc.code) from exc
    chat.busy = True  # no await between the check and here; the run's task clears it
    queue = launch(
        Job(
            settings=settings,
            guard=state.crawl_guard,
            runner=state.chat_runner,
            slots=state.crawl_slots,
            store=state.store,
            memory=memory,
            chat=chat,
            message=body.message,
        )
    )

    async def events() -> AsyncIterator[str]:
        while (event := await queue.get()) is not None:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/chat/runs/{run_id}/log",
    operation_id="getChatRunLog",
    dependencies=[ReviewerAuth],
    response_class=Response,
    responses={
        200: {"content": {CONTENT_TYPE: {"schema": {"type": "string"}}}},
        **{code: {"model": Error} for code in (401, 404, 503)},
    },
)
async def get_chat_run_log(run_id: UUID, request: Request) -> Response:
    store = request.app.state.store
    if store is None:
        raise ApiError(503, "Object storage is not configured", "storage_missing")
    try:
        body = await run_in_threadpool(store.get, run_log_key("chat", str(run_id)))
    except Exception as exc:
        raise ApiError(503, "Object storage is unreachable", "storage_unavailable") from exc
    if body is None:
        raise ApiError(404, "Run log not found", "not_found")
    return Response(body, media_type=CONTENT_TYPE)
