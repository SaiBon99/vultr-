# Audit and receipts

## Purpose
Every state change appends to a SHA-256 hash chain, and every decision produces an Ed25519-signed receipt in Object Storage. Reasons: D4. Code: `backend/app/audit.py`, `backend/app/receipts.py`.

## Requirements

### Requirement: Append-only chain
audit_events SHALL reject UPDATE and DELETE, and GET /audit SHALL report chain_valid over the full chain.

#### Scenario: Tampered row
- **WHEN** any event payload changes after insert
- **THEN** chain_valid is false and first_invalid_seq names that row

### Requirement: Verifiable receipts
Each purge or override SHALL produce a receipt signed per contracts/README.md that the browser verifies with GET /keys/public.

#### Scenario: Browser verification
- **WHEN** the reviewer opens a receipt
- **THEN** Web Crypto verifies it, and a tampered copy fails
