"""Builds the shared MemoryService once, from settings. Only this process holds DATABASE_URL."""

import asyncio

from openai import AsyncOpenAI

from ..config import load_settings
from .honeypot import FIXTURES
from .judge import Judge
from .service import MemoryService
from .store import PostgresStore

_memory: MemoryService | None = None
_lock = asyncio.Lock()


async def get_memory() -> MemoryService:
    global _memory
    if _memory is not None:
        return _memory
    async with _lock:
        if _memory is None:
            settings = load_settings()
            if not settings.database_url:
                raise RuntimeError("DATABASE_URL must be set (see .env.example)")
            store = await PostgresStore.connect(settings.database_url)
            judge = None
            if settings.judge_model and settings.inference_api_key:
                judge = Judge(
                    AsyncOpenAI(base_url=settings.inference_base_url, api_key=settings.inference_api_key),
                    settings.judge_model,
                )
            _memory = MemoryService(
                store=store,
                default_gate_mode=settings.gate_mode,
                allowed_domains=settings.allowed_domains,
                judge=judge,
                fixtures=FIXTURES,
            )
    return _memory
