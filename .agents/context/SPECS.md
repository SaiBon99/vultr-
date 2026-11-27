# Specs

What each capability does now, one spec each in `openspec/specs/<capability>/spec.md`; proposals go in `openspec/changes/`. A spec is `## Purpose` then `## Requirements` with `### Requirement:` blocks (SHALL) and `#### Scenario:` WHEN/THEN lines. Budget 6 KB a spec.

| Capability | Spec | Code |
| :--- | :--- | :--- |
| Memory gate | [memory-gate](../../openspec/specs/memory-gate/spec.md) | `backend/app/gate.py` |
| Quarantine review | [quarantine-review](../../openspec/specs/quarantine-review/spec.md) | `backend/app/routes/`, `frontend/src/` |
| Audit and receipts | [audit-receipts](../../openspec/specs/audit-receipts/spec.md) | `backend/app/audit.py`, `backend/app/receipts.py` |

Open change: [add-chat-agent](../../openspec/changes/add-chat-agent/proposal.md) (D10). Open change: [refine-verdicts-and-rulebook](../../openspec/changes/refine-verdicts-and-rulebook/proposal.md) (D5; main specs already reflect it).
