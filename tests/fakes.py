"""In-memory stand-ins for the Postgres store and the judge. Same method names, no network."""

from datetime import datetime, timezone

from backend.app.memory.store import GENESIS_HASH, chain_hash, payload_hash
import json


class InMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.memories: list[dict] = []
        self.quarantine: list[dict] = []
        self.poison: dict[str, frozenset[int]] = {}
        self.audit: list[dict] = []
        self.reads: list[dict] = []
        self._next_id = 1

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def create_session(self, session_id, label, gate_mode, namespace):
        self.sessions[session_id] = {"session_id": session_id, "label": label, "gate_mode": gate_mode,
                                     "namespace": namespace, "tainted": False, "write_count": 0}

    async def get_session(self, session_id):
        s = self.sessions.get(session_id)
        return dict(s) if s else None

    async def mark_tainted(self, session_id):
        self.sessions[session_id]["tainted"] = True

    async def increment_writes(self, session_id):
        self.sessions[session_id]["write_count"] += 1
        return self.sessions[session_id]["write_count"]

    async def add_read(self, session_id, ref, content):
        read_id = f"r{len(self.reads) + 1}"
        self.reads.append({"read_id": read_id, "session_id": session_id, "ref": ref, "content": content})
        return read_id

    async def insert_memory(self, session_id, namespace, content, provenance):
        row = {"id": self._id(), "session_id": session_id, "namespace": namespace, "content": content,
               "provenance": provenance, "payload_hash": payload_hash(content)}
        self.memories.append(row)
        return row["id"]

    async def active_memories(self, namespace, limit=50):
        return [m for m in self.memories if m.get("namespace") == namespace]

    async def insert_quarantine(self, session_id, content, verdict, flags):
        row = {"id": self._id(), "session_id": session_id, "content": content, "verdict": verdict,
               "flags": list(flags), "judge_note": None, "status": "quarantined",
               "payload_hash": payload_hash(content), "override_reason": None}
        self.quarantine.append(row)
        return row["id"]

    async def quarantine_rows(self, status="quarantined"):
        return [dict(r) for r in self.quarantine if r["status"] == status]

    async def get_quarantine(self, row_id):
        for r in self.quarantine:
            if r["id"] == row_id:
                return dict(r)
        return None

    async def set_judge_note(self, row_id, note, verdict):
        for r in self.quarantine:
            if r["id"] == row_id:
                r["judge_note"] = note
                r["verdict"] = verdict

    async def purge_quarantine(self, row_id, fingerprint):
        for r in self.quarantine:
            if r["id"] == row_id:
                self.poison[r["payload_hash"]] = frozenset(fingerprint)
                r["content"] = None
                r["status"] = "purged"

    async def override_quarantine(self, row_id, reason):
        for r in self.quarantine:
            if r["id"] == row_id:
                r["status"] = "overridden"
                r["override_reason"] = reason
                namespace = self.sessions[r["session_id"]]["namespace"]
                self.memories.append({"id": self._id(), "session_id": r["session_id"], "namespace": namespace,
                                      "content": r["content"], "provenance": "reviewed",
                                      "payload_hash": r["payload_hash"]})

    async def confirmed_fingerprints(self):
        return list(self.poison.values())

    async def append_audit(self, event_type, payload):
        prev = self.audit[-1]["event_hash"] if self.audit else GENESIS_HASH
        body = json.dumps(payload, sort_keys=True)
        digest = chain_hash(prev, event_type, body)
        self.audit.append({"event_type": event_type, "payload": body, "prev_hash": prev, "event_hash": digest,
                           "created_at": datetime.now(timezone.utc)})
        return digest

    async def list_audit(self, limit=200):
        return list(reversed(self.audit))[:limit]


class FakeJudge:
    def __init__(self, reply=None, error: Exception | None = None) -> None:
        self.reply = reply or {"summary": "Instructs the assistant to reroute orders.", "risk_level": "high",
                               "recommended_action": "purge"}
        self.error = error
        self.calls: list[tuple[str, str, list[str]]] = []

    async def explain(self, content, provenance, flags):
        self.calls.append((content, provenance, flags))
        if self.error:
            raise self.error
        return dict(self.reply)
