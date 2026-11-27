"""Store proposed memory writes in Postgres (contracts/schema.sql, Option B).

The gate decides, this file only stores: CLEAN -> memories, anything else -> quarantine_queue.
Callers pass a connection from the quarantine_proxy role (DATABASE_URL_PROXY), never memory_reader.
shortcut: no audit_events rows yet; add the hash-chained append before the demo.
"""

import secrets
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app import gate
from app.canonical import payload_hash
from app.deps import token_hash

# shortcut: gate.py still returns the pre-D5 names; map to the schema's verdicts until it is updated.
DB_VERDICT = {
    gate.TAINTED_UNREVIEWED: "NEEDS_REVIEW",
    gate.POLICY_BLOCKED: "BLOCKED",
    gate.INCONCLUSIVE: "FAIL_CLOSED",
}

# Flag weights from contracts/openapi.yaml (x-rulebook on RuleFlag).
WEIGHTS = {
    "tainted_session": 25,
    "immediate_write_after_read": 10,
    "write_burst": 15,
    "overwrite_attempt": 25,
    "imperative_directive": 40,
    "external_email": 45,
    "external_url": 45,
    "sensitive_tool": 45,
    "canary_overlap": 90,
    "poison_similarity": 90,
}


def risk_score(db_verdict: str, flags: tuple[str, ...]) -> int:
    """min(100, sum of weights); FAIL_CLOSED is floored at 85 (contracts/README.md)."""
    score = min(100, sum(WEIGHTS.get(f, 0) for f in flags))
    return max(85, score) if db_verdict == "FAIL_CLOSED" else score


async def create_session(conn: AsyncConnection, gate_mode: str = "quarantined") -> tuple[UUID, str]:
    """New session row. Returns (session_id, token); only sha256(token) is stored."""
    token = secrets.token_urlsafe(32)
    async with conn.transaction():
        cur = await conn.execute(
            "INSERT INTO sessions (token_hash, gate_mode) VALUES (%s, %s) RETURNING id",
            (token_hash(token), gate_mode),
        )
        row = await cur.fetchone()
    assert row is not None
    return row[0], token


async def mark_tainted(
    conn: AsyncConnection, session_id: UUID, source_ref: str, source_kind: str
) -> None:
    """Sticky taint: record the external read. Taint never flips back to false."""
    async with conn.transaction():
        await conn.execute(
            """UPDATE sessions
               SET tainted = true,
                   writes_since_last_read = 0,
                   external_sources = external_sources || jsonb_build_array(jsonb_build_object(
                       'source_ref', %s::text, 'source_kind', %s::text, 'read_at', now()))
               WHERE id = %s""",
            (source_ref, source_kind, session_id),
        )


def judge_failure_update(
    verdict: str, score: int, flags: list[str]
) -> tuple[str, int, list[str]]:
    """Judge timeout or bad JSON (contracts/README.md): add judge_failed; NEEDS_REVIEW escalates
    to FAIL_CLOSED with score >= 85; BLOCKED and FAIL_CLOSED keep verdict and score."""
    flags = flags if "judge_failed" in flags else [*flags, "judge_failed"]
    if verdict == "NEEDS_REVIEW":
        return "FAIL_CLOSED", max(score, 85), flags
    return verdict, score, flags


async def record_judgement(conn: AsyncConnection, quarantine_id: UUID, result: Any) -> str:
    """Store the judge's note on a frozen row. The judge explains; it never lowers a verdict.
    Only rows still pending are touched, so a late judge cannot overwrite a decision."""
    async with conn.transaction():
        if result.status == "done" and result.note is not None:
            await conn.execute(
                "UPDATE quarantine_queue SET judge_status = 'done', judge_note = %s"
                " WHERE id = %s AND judge_status = 'pending'",
                (Jsonb(result.note.model_dump()), quarantine_id),
            )
            return "done"
        cur = await conn.execute(
            "SELECT verdict, risk_score, rule_flags FROM quarantine_queue"
            " WHERE id = %s AND judge_status = 'pending' FOR UPDATE",
            (quarantine_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return "skipped"
        verdict, score, flags = judge_failure_update(row[0], row[1], list(row[2]))
        await conn.execute(
            "UPDATE quarantine_queue SET judge_status = 'failed', verdict = %s, risk_score = %s,"
            " rule_flags = %s WHERE id = %s",
            (verdict, score, Jsonb(flags), quarantine_id),
        )
        return "failed"


def notes_from_crawl(result: Any) -> list[str]:
    """What a crawl remembers: one note with the summary and key points, so the gate sees both.
    One write per run keeps the burst rule quiet."""
    return ["\n".join([result.summary, *result.key_points])]


async def save_crawl(
    conn: AsyncConnection,
    result: Any,
    allowlist: frozenset[str],
    canaries: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """One new session per crawl, tainted by every page it read; the note goes through the gate."""
    session_id, _token = await create_session(conn)
    for page in result.pages:
        if page.status == "ok" and page.final_url:
            await mark_tainted(conn, session_id, page.final_url, "web")
    return [
        await write_memory(conn, session_id, note, allowlist, canaries)
        for note in notes_from_crawl(result)
    ]


async def write_memory(
    conn: AsyncConnection,
    session_id: UUID,
    content: str,
    allowlist: frozenset[str],
    canaries: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Run the gate on one proposed write and store it in the table the verdict picks."""
    async with conn.transaction():
        cur = await conn.execute(
            "SELECT tainted, write_count, external_sources FROM sessions WHERE id = %s FOR UPDATE",
            (session_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError("unknown session")
        tainted, write_count, sources = row

        result = gate.evaluate(
            gate.GateInput(
                content=content,
                session_tainted=tainted,
                prior_write_count=write_count,
                allowlist=allowlist,
                canaries=canaries,
            )
        )
        digest = payload_hash(content)
        source_ref = sources[-1]["source_ref"] if sources else None
        await conn.execute(
            "UPDATE sessions SET write_count = write_count + 1,"
            " writes_since_last_read = writes_since_last_read + 1 WHERE id = %s",
            (session_id,),
        )

        if result.verdict == gate.CLEAN_USER:
            cur = await conn.execute(
                "INSERT INTO memories (session_id, content, source, source_ref, payload_hash)"
                " VALUES (%s, %s, 'user', %s, %s) RETURNING id",
                (session_id, content, source_ref, digest),
            )
            table, verdict, score = "memories", "ALLOW", 0
        else:
            verdict = DB_VERDICT.get(result.verdict, "FAIL_CLOSED")  # unknown verdict fails closed
            score = risk_score(verdict, result.rule_flags)
            cur = await conn.execute(
                "INSERT INTO quarantine_queue (session_id, content, payload_hash, source, source_ref,"
                " verdict, risk_score, rule_flags) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                " RETURNING id",
                (
                    session_id,
                    content,
                    digest,
                    "external" if tainted else "user",
                    source_ref,
                    verdict,
                    score,
                    Jsonb(list(result.rule_flags)),
                ),
            )
            table = "quarantine_queue"
        new = await cur.fetchone()
    assert new is not None
    return {
        "table": table,
        "id": new[0],
        "verdict": verdict,
        "risk_score": score,
        "rule_flags": list(result.rule_flags),
        "payload_hash": digest,
        "content": content,
    }
