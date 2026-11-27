# Refine verdicts and rulebook

## Why
The first contract used TAINTED_UNREVIEWED / POLICY_BLOCKED / INCONCLUSIVE with INCONCLUSIVE below POLICY_BLOCKED, no numeric priority, and no handling for hidden characters, write-right-after-read laundering or judge failure on a review-tier row. The [Execution Plan threat model](../../../docs/Execution%20Plan.md#threat-model-and-detection) defines a stricter, still fully deterministic model (D5).

## What Changes
- **BREAKING** Verdicts become ALLOW / NEEDS_REVIEW / BLOCKED / FAIL_CLOSED with precedence FAIL_CLOSED > BLOCKED > NEEDS_REVIEW > ALLOW.
- 13 rule flags (adds immediate_write_after_read) with weights in a machine-readable x-rulebook on RuleFlag.
- Integer risk_score (0-100, FAIL_CLOSED floor 85) on quarantined writes, quarantine items and receipts; effective_priority_score adds a +15 judge boost for review ordering only.
- Stage 0 strips zero-width, tag and bidi characters from an inspection copy; the hash covers raw bytes.
- Judge failure escalates NEEDS_REVIEW to FAIL_CLOSED; BLOCKED stays BLOCKED.
- Override requires a reason for BLOCKED and FAIL_CLOSED and checks payload_hash; receipts are only purged or overridden.
- Pattern A endpoints: GET / (redirect to /ui/), POST /demo/run, GET /demo/runs with sandbox caps (512 MB, 1 CPU, 30 s).

## Capabilities
- Modified: `memory-gate`, `quarantine-review`.

## Impact
- contracts/: schema.sql (writes_since_last_read, risk_score, reason constraint), openapi.yaml 0.2.0, receipt and judge schemas, README, fixtures and check.
- Tracks in Phase 1: infra/sql/001_init.sql must mirror schema.sql; backend models, gate, routes and demo runner; frontend types, badges, priority queue and runner tab.
