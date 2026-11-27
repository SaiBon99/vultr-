"""Offline doubles for /chat: an in-memory ChatMemory that runs the real gate, and a scripted model.

The model is a local HTTP server like the crawl tests use, so the real model code path runs. The
agent is the real sandbox/chat_agent.py as a local subprocess (crawl_fakes.FakeRunner).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app import gate, memory_store
from app.canonical import payload_hash
from tests.crawl_fakes import FakeRunner, LocalServer, chat_reply

CHAT_AGENT = Path(__file__).resolve().parents[1] / "sandbox" / "chat_agent.py"


class ChatFakeRunner(FakeRunner):
    agent = CHAT_AGENT


class FakeMemory:
    """Same decisions as memory_store.write_memory (the real gate), kept in dicts."""

    available = True

    def __init__(self, allowlist: frozenset[str] = frozenset()) -> None:
        self.allowlist = allowlist
        self.sessions: dict[UUID, dict[str, Any]] = {}
        self.memories: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, Any]] = []
        self.fail = False  # every call raises, like a database that went away
        self.reads: list[UUID] = []

    def _check(self) -> None:
        if self.fail:
            raise RuntimeError("database down")

    async def create_session(self) -> UUID:
        self._check()
        sid = uuid4()
        self.sessions[sid] = {"tainted": False, "writes": 0, "refs": []}
        return sid

    async def mark_tainted(self, session_id: UUID, source_ref: str) -> None:
        self._check()
        s = self.sessions[session_id]
        s["tainted"] = True
        s["refs"].append(source_ref)

    async def remember(self, session_id: UUID, content: str) -> dict[str, Any]:
        self._check()
        s = self.sessions[session_id]
        result = gate.evaluate(
            gate.GateInput(
                content=content,
                session_tainted=s["tainted"],
                prior_write_count=s["writes"],
                allowlist=self.allowlist,
            )
        )
        s["writes"] += 1
        row = {"id": uuid4(), "session_id": session_id, "content": content}
        digest = payload_hash(content)
        if result.verdict == gate.CLEAN_USER:
            self.memories.append(row)
            return {
                "table": "memories",
                "id": row["id"],
                "verdict": "ALLOW",
                "risk_score": 0,
                "rule_flags": [],
                "payload_hash": digest,
            }
        verdict = memory_store.DB_VERDICT.get(result.verdict, "FAIL_CLOSED")
        self.quarantine.append(row)
        return {
            "table": "quarantine_queue",
            "id": row["id"],
            "verdict": verdict,
            "risk_score": memory_store.risk_score(verdict, result.rule_flags),
            "rule_flags": list(result.rule_flags),
            "payload_hash": digest,
        }

    async def recall(self, session_id: UUID, query: str | None) -> list[dict[str, Any]]:
        self._check()
        self.reads.append(session_id)  # memories only: this fake has no path to quarantine
        rows = [m for m in self.memories if m["session_id"] == session_id]
        if query:
            rows = [m for m in rows if query.lower() in m["content"].lower()]
        return [{"id": m["id"], "content": m["content"]} for m in reversed(rows)][:10]


class ScriptedModel:
    """A local inference server that answers with the next scripted message content.

    script items are strings (the model's message content) or dicts, which are JSON-encoded.
    When the script runs out it replies {"reply": "done"}. `requests` holds every parsed body.
    """

    def __init__(self, script: list[str | dict] | None = None, on_call=None) -> None:
        self.server = LocalServer()
        self.script = list(script or [])
        self.requests: list[dict[str, Any]] = []
        self.on_call = on_call  # called with the parsed request body before each answer
        self.server.routes["/v1/chat/completions"] = (
            200,
            {"Content-Type": "application/json"},
            self._answer,
        )

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.port}/v1"

    def _answer(self, body: bytes) -> bytes:
        request = json.loads(body)
        self.requests.append(request)
        if self.on_call is not None:
            self.on_call(request)
        item = self.script.pop(0) if self.script else {"reply": "done"}
        content = item if isinstance(item, str) else json.dumps(item)
        return chat_reply(
            content,
            completion_id=f"cmpl-{len(self.requests)}",
            usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        )

    def close(self) -> None:
        self.server.close()
