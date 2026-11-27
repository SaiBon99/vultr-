"""The chat's view of the memory store: one session per chat, gated writes, memories-only recall.

ChatMemory is the seam tests replace; PgChatMemory is the real one. Writes use the
quarantine_proxy pool through app.memory_store; recall uses the memory_reader pool and reads the
`memories` table only, never quarantine_queue.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app import gate, memory_store
from app.config import Settings
from app.db import Database

RECALL_LIMIT = 10


class ChatMemory(Protocol):
    @property
    def available(self) -> bool: ...

    async def create_session(self) -> UUID: ...

    async def mark_tainted(self, session_id: UUID, source_ref: str) -> None: ...

    async def remember(self, session_id: UUID, content: str) -> dict[str, Any]: ...

    async def recall(self, session_id: UUID, query: str | None) -> list[dict[str, Any]]: ...


class PgChatMemory:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.allowlist = gate.normalize_allowlist(settings.egress_allowlist)

    @property
    def available(self) -> bool:
        return self.db.configured

    async def create_session(self) -> UUID:
        assert self.db.proxy is not None
        async with self.db.proxy.connection() as conn:
            session_id, _token = await memory_store.create_session(conn)
        return session_id

    async def mark_tainted(self, session_id: UUID, source_ref: str) -> None:
        assert self.db.proxy is not None
        async with self.db.proxy.connection() as conn:
            await memory_store.mark_tainted(conn, session_id, source_ref, "web")

    async def remember(self, session_id: UUID, content: str) -> dict[str, Any]:
        assert self.db.proxy is not None
        async with self.db.proxy.connection() as conn:
            return await memory_store.write_memory(conn, session_id, content, self.allowlist)

    async def recall(self, session_id: UUID, query: str | None) -> list[dict[str, Any]]:
        """Newest first, at most RECALL_LIMIT, optionally those containing the query."""
        assert self.db.reader is not None
        sql = "SELECT id, content FROM memories WHERE session_id = %s"
        params: list[Any] = [session_id]
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " AND content ILIKE %s"
            params.append(f"%{escaped}%")
        sql += " ORDER BY created_at DESC, id LIMIT %s"
        params.append(RECALL_LIMIT)
        async with self.db.reader.connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [{"id": row[0], "content": row[1]} for row in rows]
