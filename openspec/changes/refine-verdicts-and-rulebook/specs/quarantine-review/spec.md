## ADDED Requirements

### Requirement: Deal Desk demo runner
POST /demo/run SHALL run the Deal Desk agent once in a disposable sandbox capped at 512 MB, 1 CPU and 30 s with no DB, S3 or LLM credentials and no direct egress, behind X-Reviewer-Token; GET /demo/runs SHALL list runs with stdout, stderr, quote output and containment. gate_mode naive SHALL require DEMO_ALLOW_NAIVE.

#### Scenario: Quarantined run contains the leak
- **WHEN** a reviewer runs research_then_quote with gate_mode quarantined
- **THEN** containment.leaked is false and blocked_egress lists the denied direct connections

## MODIFIED Requirements

### Requirement: Session-grouped queue
GET /quarantine SHALL return rows grouped by session, behind X-Reviewer-Token, with source snippet, verdict, risk_score, effective_priority_score, rule flags and judge note; items SHALL sort by (effective_priority_score DESC, created_at DESC) and sessions by their top item, where effective_priority_score adds 15 when the judge recommends purge at high or critical risk.

#### Scenario: Judge raises priority
- **WHEN** two rows have risk_score 100 and only one has a critical purge judge note
- **THEN** that row sorts first with effective_priority_score 115

#### Scenario: Pending judge
- **WHEN** a row was just frozen
- **THEN** judge_status is pending and the UI shows "Evaluating..."

### Requirement: Decisions
Purge SHALL null content and keep payload_hash and embedding as a tombstone. Override SHALL verify sha256(utf8(content)) == payload_hash (409 otherwise) and copy the row to memories as external_override. Overriding BLOCKED or FAIL_CLOSED SHALL require a non-blank reason; NEEDS_REVIEW reason is optional. Receipts SHALL be signed only at these decisions and SHALL include risk_score.

#### Scenario: Override without reason
- **WHEN** the reviewer overrides a FAIL_CLOSED row with an empty reason
- **THEN** the API returns 422 and the row stays quarantined

#### Scenario: Tampered content
- **WHEN** a quarantined row's content no longer hashes to payload_hash
- **THEN** override returns 409 payload_hash_mismatch
