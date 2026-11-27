"""FastAPI app factory. Run: uv run uvicorn app.main:app --port 8000"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.db import Database
from app.deps import ApiError
from app.receipts import S3ObjectStore, Signer
from app.routes import audit, proxy, public, quarantine

FRONTEND_BUILD = Path(__file__).resolve().parents[2] / "frontend" / "build"


def _build_store(settings: Settings) -> S3ObjectStore | None:
    if not settings.S3_ENDPOINT_URL:
        return None
    return S3ObjectStore(
        endpoint_url=settings.S3_ENDPOINT_URL,
        access_key=settings.S3_ACCESS_KEY.get_secret_value(),
        secret_key=settings.S3_SECRET_KEY.get_secret_value(),
        bucket=settings.S3_BUCKET,
        region=settings.S3_REGION,
    )


def _build_signer(settings: Settings) -> Signer | None:
    path = settings.RECEIPT_SIGNING_KEY_PATH
    return Signer.from_path(path) if path and Path(path).is_file() else None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await db.open()
        try:
            yield
        finally:
            await db.close()

    app = FastAPI(title="Memory Quarantine Proxy", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.store = _build_store(settings)
    app.state.signer = _build_signer(settings)
    app.state.judge = None  # Phase 1: OpenAIJudge(settings) when VULTR_INFERENCE_API_KEY is set

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        body = {"detail": str(exc.detail)}
        if isinstance(exc, ApiError) and exc.code:
            body["code"] = exc.code
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(
            {"detail": "; ".join(parts), "code": "validation_error"}, status_code=422
        )

    app.include_router(public.router)
    app.include_router(proxy.router)
    app.include_router(quarantine.router)
    app.include_router(audit.router)

    if FRONTEND_BUILD.is_dir():
        app.mount("/ui", StaticFiles(directory=FRONTEND_BUILD, html=True), name="ui")
    return app


app = create_app()
