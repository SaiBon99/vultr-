"""Memory quarantine logic behind the proxy routes. Storage and the judge are injected, so tests use fakes."""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from .gate import (
    SIMILARITY_THRESHOLD,
    Verdict,
    WriteFacts,
    evaluate,
    fingerprint,
    max_similarity,
)
from .store import payload_hash


class ReviewError(ValueError):
    """A review action was refused, for example a POLICY_BLOCKED override without a typed reason."""


class MemoryStore(Protocol):
    async def create_session(self, session_id: str, label: str, gate_mode: str, namespace: str) -> None: ...
    async def get_session(self, session_id: str) -> dict | None: ...
    async def mark_tainted(self, session_id: str) -> None: ...
    async def increment_writes(self, session_id: str) -> int: ...
    async def add_read(self, session_id: str, ref: str, content: str) -> str: ...
    async def insert_memory(self, session_id: str, namespace: str, content: str, provenance: str) -> int: ...
    async def active_memories(self, namespace: str, limit: int = 50) -> list[dict]: ...
    async def insert_quarantine(self, session_id: str, content: str, verdict: str, flags: list[str]) -> int: ...
    async def quarantine_rows(self, status: str = "quarantined") -> list[dict]: ...
    async def get_quarantine(self, row_id: int) -> dict | None: ...
    async def set_judge_note(self, row_id: int, note: dict | None, verdict: str) -> None: ...
    async def purge_quarantine(self, row_id: int, fingerprint: list[int]) -> None: ...
    async def override_quarantine(self, row_id: int, reason: str | None) -> None: ...
    async def confirmed_fingerprints(self) -> list[frozenset[int]]: ...
    async def append_audit(self, event_type: str, payload: dict) -> str: ...
    async def list_audit(self, limit: int = 200) -> list[dict]: ...


class Explainer(Protocol):
    async def explain(self, content: str, provenance: str, flags: list[str]) -> dict: ...


@dataclass
class WriteResult:
    status: str  # "active" or "quarantined"
    verdict: str
    flags: list[str]
    row_id: int


GATE_MODES = {"gated", "naive"}


@dataclass
class MemoryService:
    store: MemoryStore
    # Default for sessions created in-process. "naive" is the demo baseline that bypasses the gate.
    # The mode is stored on the session by trusted host code, so a sandbox cannot change it.
    default_gate_mode: str = "gated"
    allowed_domains: frozenset[str] = frozenset()
    judge: Explainer | None = None
    fixtures: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.default_gate_mode not in GATE_MODES:
            raise ValueError(f"unknown gate_mode: {self.default_gate_mode}")

    async def _audit(self, event_type: str, payload: dict) -> None:
        await self.store.append_audit(event_type, payload)

    async def _require_session(self, session_id: str) -> dict:
        session = await self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id}")
        return session

    async def create_session(self, label: str = "", gate_mode: str | None = None, namespace: str = "default") -> str:
        """Host-only. Not exposed over HTTP, so a sandbox cannot mint a session with a weaker gate or namespace."""
        mode = gate_mode or self.default_gate_mode
        if mode not in GATE_MODES:
            raise ValueError(f"unknown gate_mode: {mode}")
        session_id = uuid4().hex[:16]
        await self.store.create_session(session_id, label, mode, namespace)
        await self._audit(
            "session_created", {"session_id": session_id, "label": label, "gate_mode": mode, "namespace": namespace}
        )
        return session_id

    async def read(self, session_id: str, ref: str) -> dict:
        """External read. Sticky taint: every later write in this session is treated as tainted."""
        await self._require_session(session_id)
        if ref not in self.fixtures:
            raise KeyError(f"unknown ref {ref}")
        content = self.fixtures[ref]
        await self.store.mark_tainted(session_id)
        read_id = await self.store.add_read(session_id, ref, content)
        await self._audit(
            "external_read",
            {"session_id": session_id, "ref": ref, "read_id": read_id, "content_sha256": payload_hash(content)},
        )
        return {"read_id": read_id, "ref": ref, "content": content}

    async def write(self, session_id: str, content: str) -> WriteResult:
        session = await self._require_session(session_id)
        writes = await self.store.increment_writes(session_id)

        if session["gate_mode"] == "naive":
            row_id = await self.store.insert_memory(session_id, session["namespace"], content, "unchecked")
            await self._audit("write_naive", {"session_id": session_id, "memory_id": row_id})
            return WriteResult("active", "NAIVE", [], row_id)

        known = await self.store.confirmed_fingerprints()
        similar = bool(content.strip()) and max_similarity(content, known) >= SIMILARITY_THRESHOLD
        facts = WriteFacts(
            content=content,
            session_id=session_id,
            session_tainted=bool(session["tainted"]),
            writes_in_session=writes,
            overwrites_existing=False,  # the gate is insert-only; nothing overwrites an active row
            confirmed_poison_similar=similar,
        )
        decision = evaluate(facts, self.allowed_domains)

        if decision.verdict is Verdict.CLEAN_USER:
            row_id = await self.store.insert_memory(session_id, session["namespace"], content, "user")
            await self._audit(
                "write_clean", {"session_id": session_id, "memory_id": row_id, "content_sha256": payload_hash(content)}
            )
            return WriteResult("active", decision.verdict.value, [], row_id)

        flags = list(decision.flags)
        verdict = decision.verdict
        row_id = await self.store.insert_quarantine(session_id, content or "", verdict.value, flags)
        await self._audit(
            "write_quarantined",
            {"session_id": session_id, "row_id": row_id, "verdict": verdict.value, "flags": flags},
        )

        if self.judge is not None and content.strip():
            provenance = "external" if session["tainted"] else "user"
            try:
                note = await self.judge.explain(content, provenance, flags)
                await self.store.set_judge_note(row_id, note, verdict.value)
                await self._audit("judge_explained", {"row_id": row_id, "risk_level": note["risk_level"]})
            except Exception as exc:  # noqa: BLE001 - any judge failure (parse or network) fails closed
                verdict = Verdict.INCONCLUSIVE
                flags.append("judge_failure")
                await self.store.set_judge_note(row_id, {"error": str(exc)[:200]}, verdict.value)
                await self._audit("judge_failed", {"row_id": row_id, "error": str(exc)[:200]})

        return WriteResult("quarantined", verdict.value, flags, row_id)

    async def recall_for(self, session_id: str) -> list[dict]:
        """Active rows in the session's namespace only. Quarantined rows are never returned."""
        session = await self._require_session(session_id)
        return await self.store.active_memories(session["namespace"])

    async def recall(self, namespace: str = "default") -> list[dict]:
        return await self.store.active_memories(namespace)

    async def review_queue(self) -> list[dict]:
        return await self.store.quarantine_rows("quarantined")

    async def purge(self, row_id: int) -> None:
        row = await self._pending_row(row_id)
        fp = sorted(fingerprint(row["content"] or ""))
        await self.store.purge_quarantine(row_id, fp)
        await self._audit("purge", {"row_id": row_id, "payload_sha256": row["payload_hash"]})

    async def override(self, row_id: int, reason: str | None) -> None:
        row = await self._pending_row(row_id)
        if row["verdict"] == Verdict.POLICY_BLOCKED.value and not (reason and reason.strip()):
            raise ReviewError("POLICY_BLOCKED overrides require a typed reason")
        await self.store.override_quarantine(row_id, reason.strip() if reason else None)
        await self._audit(
            "override",
            {"row_id": row_id, "verdict": row["verdict"], "reason": reason, "payload_sha256": row["payload_hash"]},
        )

    async def _pending_row(self, row_id: int) -> dict:
        row = await self.store.get_quarantine(row_id)
        if row is None:
            raise KeyError(f"unknown quarantine row {row_id}")
        if row["status"] != "quarantined":
            raise ReviewError(f"row {row_id} is already {row['status']}")
        return row
