# Quarantine review

## Purpose
A reviewer inspects frozen writes grouped by session and purges or overrides each row. Reasons: D1, D2. Code: `backend/app/routes/`, `frontend/src/`.

## Requirements

### Requirement: Session-grouped queue
GET /quarantine SHALL return rows grouped by session with source snippet, rule flags and judge note, behind X-Reviewer-Token.

#### Scenario: Reviewer opens the queue
- **WHEN** the reviewer loads the Review UI
- **THEN** each session shows its external sources and quarantined rows

### Requirement: Decisions
Purge SHALL null content and keep payload_hash and embedding; override SHALL copy the row to memories as external_override; overriding POLICY_BLOCKED SHALL require a non-blank reason.

#### Scenario: Override without reason
- **WHEN** the reviewer overrides a POLICY_BLOCKED row with an empty reason
- **THEN** the API returns 422 and the row stays quarantined
