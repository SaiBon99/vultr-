"""One NDJSON transcript per sandbox run in Object Storage (contracts/README.md wire rule 6).

Lines: run_start, then msg/host lines in order (seq counts up across both, t_ms since run_start),
then run_end. Lines are kept whole in memory; to_bytes() redacts secrets first, then applies the
caps (so no cut can leave a fragment of a secret), keeps the object under OBJECT_CAP, and the
caller hashes the result.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.crawl.runner import STDERR_LIMIT, Limits
from app.storage import ObjectStore

log = logging.getLogger("app.runlog")

CONTENT_TYPE = "application/x-ndjson"
HOST_TO_AGENT = "host_to_agent"
AGENT_TO_HOST = "agent_to_host"
RAW_CAP = 4096  # UTF-8 bytes of an unparseable agent line
TEXT_CAP = 16 * 1024  # UTF-8 bytes of fetch_result.body and model.page_text
OBJECT_CAP = 1024 * 1024  # bytes of the whole object
MIN_SECRET_CHARS = 8
REDACTED = "[REDACTED]"


def run_log_key(kind: str, run_id: str, session_id: str | None = None) -> str:
    if session_id:
        return f"logs/sessions/{session_id}/{run_id}.jsonl"
    return f"logs/{kind}/{run_id}.jsonl"


class RunLog:
    """Collects one run's lines in memory. The clock starts when the run log is created."""

    def __init__(
        self,
        run_id: str,
        kind: str,
        session_id: str | None,
        limits: Limits,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.run_id = run_id
        self.kind = kind
        self.session_id = session_id
        self._clock = clock
        self._t0 = clock()
        self._start: dict[str, Any] = {
            "type": "run_start",
            "run_id": run_id,
            "kind": kind,
            "session_id": session_id,
            "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limits": asdict(limits),
            "image_id": None,
        }
        self._lines: list[dict[str, Any]] = []
        self._end: dict[str, Any] | None = None

    def start(self, image_id: str | None) -> None:
        self._start["image_id"] = image_id

    def sent(self, msg: dict[str, Any]) -> None:
        self._add({"type": "msg", "dir": HOST_TO_AGENT, "msg": dict(msg)})

    def received(self, line: bytes, parsed: dict[str, Any] | None) -> None:
        if parsed is None:
            raw = line.rstrip(b"\r\n").decode("utf-8", errors="replace")
            self._add({"type": "msg", "dir": AGENT_TO_HOST, "raw": raw})
        else:
            self._add({"type": "msg", "dir": AGENT_TO_HOST, "msg": dict(parsed)})

    def host(self, event: str, **fields: Any) -> None:
        self._add({"type": "host", "event": event, **fields})

    def finish(
        self,
        *,
        status: str,
        http_status: int | None,
        error_code: str | None,
        exit_code: int | None,
        container_id: str | None,
        elapsed_ms: int,
        stderr: str,
        stderr_truncated: bool,
    ) -> None:
        self._end = {
            "type": "run_end",
            "status": status,
            "http_status": http_status,
            "error_code": error_code,
            "exit_code": exit_code,
            "container_id": container_id,
            "elapsed_ms": elapsed_ms,
            "stderr": stderr,
            "stderr_truncated": stderr_truncated,
            "lines_dropped": 0,
        }

    def _add(self, line: dict[str, Any]) -> None:
        t_ms = int((self._clock() - self._t0) * 1000)
        self._lines.append(
            {"type": line.pop("type"), "seq": len(self._lines) + 1, "t_ms": t_ms, **line}
        )

    def to_bytes(self, secrets: list[str]) -> bytes:
        """Serialize, redact each line, then keep run_start and run_end within OBJECT_CAP."""
        assert self._end is not None, "finish() before to_bytes()"
        forms = _secret_forms(secrets)

        def redact(text: str) -> str:
            for form in forms:
                text = text.replace(form, REDACTED)
            return text

        def ser(line: dict[str, Any]) -> bytes:
            return (redact(json.dumps(_capped(line, redact), ensure_ascii=False)) + "\n").encode()

        start = ser(self._start)
        # Reserve room for run_end with the largest lines_dropped it could carry.
        worst_end = ser({**self._end, "lines_dropped": len(self._lines)})
        budget = OBJECT_CAP - len(start) - len(worst_end)
        kept: list[bytes] = []
        for line in self._lines:
            body = ser(line)
            if len(body) > budget:
                break
            budget -= len(body)
            kept.append(body)
        end = ser({**self._end, "lines_dropped": len(self._lines) - len(kept)})
        return b"".join([start, *kept, end])


def _capped(line: dict[str, Any], redact: Callable[[str], str]) -> dict[str, Any]:
    """The line as stored: long text fields redacted, then cut to their caps."""
    if line["type"] == "run_end":
        stderr = redact(line["stderr"])
        kept = _clip(stderr, STDERR_LIMIT)
        return {
            **line,
            "stderr": kept,
            "stderr_truncated": line["stderr_truncated"] or kept != stderr,
        }
    if line["type"] != "msg":
        return line
    if "raw" in line:
        return {**line, "raw": _clip(redact(line["raw"]), RAW_CAP)}
    msg = line["msg"]
    if msg.get("type") == "fetch_result":
        return {**line, "msg": {"body_truncated": False, **_cut(msg, "body", redact)}}
    if msg.get("type") == "model":
        return {**line, "msg": _cut(msg, "page_text", redact)}
    return line


def _cut(msg: dict[str, Any], field: str, redact: Callable[[str], str]) -> dict[str, Any]:
    """msg with msg[field] redacted and cut to TEXT_CAP; when cut, add the full redacted text's
    length (characters) and sha256, so the kept prefix can be checked against it."""
    text = msg.get(field)
    if not isinstance(text, str):
        return msg
    text = redact(text)
    kept = _clip(text, TEXT_CAP)
    if kept == text:
        return {**msg, field: text}
    return {
        **msg,
        field: kept,
        f"{field}_truncated": True,
        f"{field}_chars": len(text),
        f"{field}_sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
    }


def _clip(text: str, cap: int) -> str:
    """At most cap UTF-8 bytes, never splitting a character."""
    data = text.encode("utf-8", errors="replace")
    return text if len(data) <= cap else data[:cap].decode("utf-8", errors="ignore")


def _secret_forms(secrets: list[str]) -> list[str]:
    """Raw and JSON-escaped forms of every secret long enough to replace, longest first."""
    forms = set()
    for secret in secrets:
        if len(secret) >= MIN_SECRET_CHARS:
            forms.add(secret)
            forms.add(json.dumps(secret, ensure_ascii=False)[1:-1])
    return sorted(forms, key=len, reverse=True)


async def upload_run_log(
    store: ObjectStore | None, runlog: RunLog, secrets: list[str]
) -> str | None:
    """Best effort: any failure is one host log line and a None URI, never an exception."""
    if store is None:
        return None
    try:
        body = runlog.to_bytes(secrets)
        metadata = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "kind": runlog.kind,
            "session-id": runlog.session_id or "",
        }
        key = run_log_key(runlog.kind, runlog.run_id, runlog.session_id)
        return await run_in_threadpool(
            store.put_bytes, key, body, content_type=CONTENT_TYPE, metadata=metadata
        )
    except Exception as exc:
        log.warning("run log upload failed run_id=%s err=%s", runlog.run_id, type(exc).__name__)
        return None
