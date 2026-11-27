"""Embedding client protocol, OpenAI-compatible stub and a deterministic offline fake."""

import hashlib
import math
from typing import Protocol

from app.config import Settings


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Deterministic unit vector from a SHA-256 stream. Equal text gives equal vectors."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        vals: list[float] = []
        counter = 0
        while len(vals) < self.dimensions:
            digest = hashlib.sha256(f"{counter}|{text}".encode()).digest()
            vals.extend((b - 127.5) / 127.5 for b in digest)
            counter += 1
        vals = vals[: self.dimensions]
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]


class OpenAIEmbedder:
    """OpenAI-compatible embeddings (qwen3-embedding-4b, 1024 dims). Stub: not exercised offline."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        self._model = settings.EMBED_MODEL
        self._dims = settings.EMBED_DIMENSIONS
        self._client = AsyncOpenAI(
            base_url=settings.VULTR_INFERENCE_BASE_URL,
            api_key=settings.VULTR_INFERENCE_API_KEY.get_secret_value(),
        )

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(
            model=self._model, input=text, dimensions=self._dims
        )
        return list(resp.data[0].embedding)
