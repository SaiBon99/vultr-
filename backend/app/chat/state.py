"""Chats live in memory on the host: chat_id -> session, capped history, busy flag.

Nothing here survives a restart (out of scope per openspec/changes/add-chat-agent).
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

HISTORY_TURNS = 20  # the last 20 user and assistant messages are sent back to the model
MAX_CHATS = 500


@dataclass
class ChatState:
    chat_id: UUID
    session_id: UUID
    created_at: datetime
    history: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=HISTORY_TURNS))
    busy: bool = False
    tainted: bool = False  # mirrors sessions.tainted, which is sticky


class Chats:
    def __init__(self, limit: int = MAX_CHATS) -> None:
        self._chats: OrderedDict[UUID, ChatState] = OrderedDict()
        self._limit = limit

    def add(self, state: ChatState) -> None:
        self._chats[state.chat_id] = state
        while len(self._chats) > self._limit:
            idle = next((cid for cid, c in self._chats.items() if not c.busy), None)
            if idle is None:
                break
            del self._chats[idle]  # oldest idle chat; its memory session stays in the database

    def get(self, chat_id: UUID) -> ChatState | None:
        return self._chats.get(chat_id)
