"""Managed PostgreSQL storage for the memory quarantine (storage option B).

Tables:
- memories: active rows only. Every recall reads this table and nothing else.
- quarantine_queue: tainted or blocked writes, held until a reviewer acts.
- confirmed_poison: fingerprints of purged rows, so similar future writes are POLICY_BLOCKED.
- audit_events: SHA-256 hash chain. Each row hashes the previous row's hash.
- sessions, reads, demo_runs: provenance and demo bookkeeping.

Only the proxy process holds DATABASE_URL. The sandbox never does.
"""

import hashlib
import json
from uuid import uuid4

import asyncpg

GENESIS_HASH = "0" * 64
AUDIT_LOCK_KEY = 4242

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    gate_mode TEXT NOT NULL DEFAULT 'gated',
    tainted BOOLEAN NOT NULL DEFAULT FALSE,
    write_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reads (
    read_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    ref TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memories (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS quarantine_queue (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    content TEXT,
    payload_hash TEXT NOT NULL,
    verdict TEXT NOT NULL,
    flags TEXT[] NOT NULL DEFAULT '{}',
    judge_note JSONB,
    status TEXT NOT NULL DEFAULT 'quarantined',
    override_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS confirmed_poison (
    payload_hash TEXT PRIMARY KEY,
    fingerprint INTEGER[] NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    seq BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,  -- stored as the exact text that was hashed (JSONB would reorder keys)
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS demo_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Migrations for tables created before namespaces existed (idempotent).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS namespace TEXT NOT NULL DEFAULT 'default';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS namespace TEXT NOT NULL DEFAULT 'default';
"""


def chain_hash(prev_hash: str, event_type: str, payload_json: str) -> str:
    """Hash of one audit event, chained to the previous event's hash."""
    material = f"{prev_hash}\n{event_type}\n{payload_json}".encode()
    return hashlib.sha256(material).hexdigest()


def payload_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _row(record) -> dict:
    return dict(record) if record is not None else None


def _decode(row: dict | None, *keys: str) -> dict | None:
    """asyncpg returns JSONB as text. Decode the named columns so callers get dicts."""
    if row is None:
        return None
    for key in keys:
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])
    return row


class PostgresStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PostgresStore":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        store = cls(pool)
        await store.ensure_schema()
        return store

    async def close(self) -> None:
        await self.pool.close()

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA)

    # sessions and provenance

    async def create_session(self, session_id: str, label: str, gate_mode: str, namespace: str) -> None:
        await self.pool.execute(
            "INSERT INTO sessions (session_id, label, gate_mode, namespace) VALUES ($1, $2, $3, $4)",
            session_id,
            label,
            gate_mode,
            namespace,
        )

    async def get_session(self, session_id: str) -> dict | None:
        return _row(
            await self.pool.fetchrow(
                "SELECT session_id, label, gate_mode, namespace, tainted, write_count FROM sessions WHERE session_id = $1",
                session_id,
            )
        )

    async def mark_tainted(self, session_id: str) -> None:
        await self.pool.execute(
            "UPDATE sessions SET tainted = TRUE WHERE session_id = $1", session_id
        )

    async def increment_writes(self, session_id: str) -> int:
        return await self.pool.fetchval(
            "UPDATE sessions SET write_count = write_count + 1 WHERE session_id = $1 RETURNING write_count",
            session_id,
        )

    async def add_read(self, session_id: str, ref: str, content: str) -> str:
        read_id = uuid4().hex[:12]
        await self.pool.execute(
            "INSERT INTO reads (read_id, session_id, ref, content) VALUES ($1, $2, $3, $4)",
            read_id,
            session_id,
            ref,
            content,
        )
        return read_id

    # memories (active) and quarantine_queue (frozen)

    async def insert_memory(self, session_id: str, namespace: str, content: str, provenance: str) -> int:
        return await self.pool.fetchval(
            "INSERT INTO memories (session_id, namespace, content, payload_hash, provenance) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            session_id,
            namespace,
            content,
            payload_hash(content),
            provenance,
        )

    async def active_memories(self, namespace: str, limit: int = 50) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT id, session_id, content, provenance FROM memories "
            "WHERE namespace = $1 ORDER BY id DESC LIMIT $2",
            namespace,
            limit,
        )
        return [dict(r) for r in rows]

    async def insert_quarantine(
        self, session_id: str, content: str, verdict: str, flags: list[str]
    ) -> int:
        return await self.pool.fetchval(
            "INSERT INTO quarantine_queue (session_id, content, payload_hash, verdict, flags) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            session_id,
            content,
            payload_hash(content),
            verdict,
            flags,
        )

    async def quarantine_rows(self, status: str = "quarantined") -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT id, session_id, content, payload_hash, verdict, flags, judge_note, status, "
            "override_reason, created_at FROM quarantine_queue WHERE status = $1 ORDER BY session_id, id",
            status,
        )
        return [_decode(dict(r), "judge_note") for r in rows]

    async def get_quarantine(self, row_id: int) -> dict | None:
        return _decode(
            _row(
                await self.pool.fetchrow(
                    "SELECT id, session_id, content, payload_hash, verdict, flags, judge_note, status "
                    "FROM quarantine_queue WHERE id = $1",
                    row_id,
                )
            ),
            "judge_note",
        )

    async def set_judge_note(self, row_id: int, note: dict | None, verdict: str) -> None:
        await self.pool.execute(
            "UPDATE quarantine_queue SET judge_note = $2::jsonb, verdict = $3 WHERE id = $1",
            row_id,
            json.dumps(note) if note is not None else None,
            verdict,
        )

    async def purge_quarantine(self, row_id: int, fingerprint: list[int]) -> None:
        """Wipe content, keep payload_hash as the tombstone, and remember the fingerprint."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE quarantine_queue SET content = NULL, status = 'purged' "
                    "WHERE id = $1 RETURNING payload_hash",
                    row_id,
                )
                if row is not None:
                    await conn.execute(
                        "INSERT INTO confirmed_poison (payload_hash, fingerprint) VALUES ($1, $2) "
                        "ON CONFLICT (payload_hash) DO NOTHING",
                        row["payload_hash"],
                        fingerprint,
                    )

    async def override_quarantine(self, row_id: int, reason: str | None) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE quarantine_queue SET status = 'overridden', override_reason = $2 "
                    "WHERE id = $1 RETURNING session_id, content",
                    row_id,
                    reason,
                )
                if row is not None:
                    namespace = await conn.fetchval(
                        "SELECT namespace FROM sessions WHERE session_id = $1", row["session_id"]
                    )
                    await conn.execute(
                        "INSERT INTO memories (session_id, namespace, content, payload_hash, provenance) "
                        "VALUES ($1, $2, $3, $4, 'reviewed')",
                        row["session_id"],
                        namespace or "default",
                        row["content"],
                        payload_hash(row["content"]),
                    )

    async def confirmed_fingerprints(self) -> list[frozenset[int]]:
        rows = await self.pool.fetch("SELECT fingerprint FROM confirmed_poison")
        return [frozenset(r["fingerprint"]) for r in rows]

    # audit and demo bookkeeping

    async def append_audit(self, event_type: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", AUDIT_LOCK_KEY)
                prev = (
                    await conn.fetchval("SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1")
                ) or GENESIS_HASH
                digest = chain_hash(prev, event_type, body)
                await conn.execute(
                    "INSERT INTO audit_events (event_type, payload, prev_hash, event_hash) "
                    "VALUES ($1, $2, $3, $4)",
                    event_type,
                    body,
                    prev,
                    digest,
                )
        return digest

    async def list_audit(self, limit: int = 200) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT seq, event_type, payload, prev_hash, event_hash, created_at "
            "FROM audit_events ORDER BY seq DESC LIMIT $1",
            limit,
        )
        return [_decode(dict(r), "payload") for r in rows]

    async def save_demo_run(self, mode: str, result: dict) -> str:
        run_id = uuid4().hex[:12]
        await self.pool.execute(
            "INSERT INTO demo_runs (run_id, mode, result) VALUES ($1, $2, $3::jsonb)",
            run_id,
            mode,
            json.dumps(result),
        )
        return run_id

    async def list_demo_runs(self) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT run_id, mode, result, created_at FROM demo_runs ORDER BY created_at DESC LIMIT 50"
        )
        return [_decode(dict(r), "result") for r in rows]


