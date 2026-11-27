"""Shapes queue rows into the GET /quarantine body (contracts/openapi.yaml). Pure: no I/O.

effective_priority_score = risk_score + 15 when the judge recommends purge at high or critical
risk. It orders the review queue only; the verdict and risk_score never change.
Items sort by (effective_priority_score DESC, created_at DESC); sessions by their top item's
effective_priority_score, then session created_at DESC.
"""

import re
from typing import Any
from uuid import UUID

from app.models import ExternalSource, QuarantineItem, QuarantineList, QuarantineSessionGroup

JUDGE_PRIORITY_BOOST = 15
_RECEIPT_KEY = re.compile(r"/receipts/([0-9a-fA-F-]{36})\.json$")


def effective_priority_score(risk_score: int, judge_note: dict[str, Any] | None) -> int:
    if (
        judge_note is not None
        and judge_note.get("recommended_action") == "purge"
        and judge_note.get("risk_level") in ("high", "critical")
    ):
        return risk_score + JUDGE_PRIORITY_BOOST
    return risk_score


def receipt_id_from_uri(receipt_uri: str | None) -> UUID | None:
    """receipt_uri is s3://<bucket>/receipts/<receipt_id>.json (contracts/schema.sql)."""
    if not receipt_uri:
        return None
    match = _RECEIPT_KEY.search(receipt_uri)
    return UUID(match.group(1)) if match else None


def _item(row: dict[str, Any]) -> QuarantineItem:
    return QuarantineItem.model_validate(
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "content": row["content"],
            "payload_hash": row["payload_hash"],
            "source": row["source"],
            "source_ref": row["source_ref"],
            # shortcut: external content is not stored, so there is no snippet to show yet.
            "source_snippet": None,
            "verdict": row["verdict"],
            "risk_score": row["risk_score"],
            "effective_priority_score": effective_priority_score(
                row["risk_score"], row["judge_note"]
            ),
            "rule_flags": row["rule_flags"],
            "judge_status": row["judge_status"],
            "judge_note": row["judge_note"],
            "override_reason": row["override_reason"],
            "decided_by": row["decided_by"],
            "decided_at": row["decided_at"],
            "receipt_uri": row["receipt_uri"],
            "receipt_id": receipt_id_from_uri(row["receipt_uri"]),
            "created_at": row["created_at"],
        }
    )


def build_queue(rows: list[dict[str, Any]]) -> QuarantineList:
    """Group rows by session and apply the contract's ordering. Input order does not matter."""
    items: dict[UUID, list[QuarantineItem]] = {}
    session_row: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        item = _item(row)
        items.setdefault(item.session_id, []).append(item)
        session_row.setdefault(item.session_id, row)

    groups: list[QuarantineSessionGroup] = []
    for session_id, session_items in items.items():
        # Stable sorts: the second key wins, the first breaks ties.
        session_items.sort(key=lambda i: i.created_at, reverse=True)
        session_items.sort(key=lambda i: i.effective_priority_score, reverse=True)
        row = session_row[session_id]
        groups.append(
            QuarantineSessionGroup(
                session_id=session_id,
                label=None,  # shortcut: sessions have no label column yet.
                gate_mode=row["gate_mode"],
                tainted=row["tainted"],
                external_sources=[ExternalSource.model_validate(s) for s in row["external_sources"]],
                write_count=row["write_count"],
                created_at=row["session_created_at"],
                items=session_items,
            )
        )

    groups.sort(key=lambda g: g.created_at, reverse=True)
    groups.sort(key=lambda g: g.items[0].effective_priority_score, reverse=True)
    return QuarantineList(sessions=groups)
