"""Audit hash chain (contracts/README.md wire rule 3)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.canonical import canon, sha256_hex

GENESIS_HASH = "sha256:" + "0" * 64
_BODY_KEYS = ("session_id", "event_type", "target_id", "payload", "created_at")


def format_ts(dt: datetime) -> str:
    """YYYY-MM-DDTHH:MM:SS.ffffffZ (UTC, microseconds). Naive datetimes are rejected."""
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now_ts() -> str:
    return format_ts(datetime.now(UTC))


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def event_hash(
    prev_hash: str,
    *,
    session_id: Any,
    event_type: str,
    target_id: Any,
    payload: Mapping[str, Any],
    created_at: str,
) -> str:
    body = {
        "session_id": _s(session_id),
        "event_type": event_type,
        "target_id": _s(target_id),
        "payload": payload,
        "created_at": created_at,
    }
    return "sha256:" + sha256_hex(prev_hash + "|" + canon(body))


@dataclass(frozen=True)
class ChainResult:
    valid: bool
    first_invalid_seq: int | None
    head_hash: str


def verify_chain(events: Iterable[Mapping[str, Any]]) -> ChainResult:
    """Walk events in ascending seq. head_hash is the stored hash of the last event."""
    prev = GENESIS_HASH
    head = GENESIS_HASH
    bad: int | None = None
    for ev in events:
        head = ev["event_hash"]
        if bad is None:
            expected = event_hash(prev, **{k: ev[k] for k in _BODY_KEYS})
            if ev["prev_hash"] != prev or ev["event_hash"] != expected:
                bad = ev["seq"]
        prev = ev["event_hash"]
    return ChainResult(bad is None, bad, head)
