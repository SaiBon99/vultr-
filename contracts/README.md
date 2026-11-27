# Contracts (frozen Phase 0)

Owner: Coordinator. Tracks read these; nobody edits them during a phase. A change goes through `openspec/changes/` and regenerates fixtures.

| File | What |
| :--- | :--- |
| [schema.sql](schema.sql) | Option B DDL: `sessions`, `memories`, `quarantine_queue`, `audit_events`, roles, grants |
| [openapi.yaml](openapi.yaml) | REST surface (OpenAPI 3.1); `components.schemas` are the wire types |
| [receipt.schema.json](receipt.schema.json) | Signed cleanup receipt |
| [judge.schema.json](judge.schema.json) | Strict judge output |
| [fixtures/](fixtures/) | Valid responses for every review endpoint; signed with an ephemeral key |
| [check_contracts.py](check_contracts.py) | Validates fixtures against the schemas and re-verifies hashes and signatures in Python |

Check: `uv run --no-project --with jsonschema --with pyyaml --with cryptography python contracts/check_contracts.py`
Regenerate fixtures: `node contracts/fixtures/generate.mjs` (new key each run, so re-run the check).

## Wire rules (backend and frontend must match byte for byte)

1. **Canonical JSON**: keys sorted by code point at every depth, separators `,` and `:` with no whitespace, UTF-8, non-ASCII unescaped, no floats. Python: `json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. JS: see `canon()` in [fixtures/generate.mjs](fixtures/generate.mjs).
2. **payload_hash**: `"sha256:" + hex(sha256(utf8(content)))`, content exactly as written (no trimming or normalization).
3. **Audit chain**: genesis `prev_hash = "sha256:" + "0"*64`. `event_hash = "sha256:" + hex(sha256(utf8(prev_hash + "|" + canon({session_id, event_type, target_id, payload, created_at}))))`. `seq` is not hashed. `created_at` is the string `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC, microseconds); the backend formats it once, stores it, and returns that exact string.
4. **Receipt signature**: Ed25519 over `utf8(canon(receipt without signature_b64))`; `signature_b64` is standard base64. `key_id` = first 16 hex chars of sha256(raw 32-byte public key). `audit_head_hash` = `event_hash` of the newest audit row before the `receipt_signed` event. Stored at `s3://quarantine-receipts/receipts/<receipt_id>.json`.
5. **Browser verification**: `crypto.subtle.importKey("jwk", jwk, {name: "Ed25519"}, false, ["verify"])`, then `verify("Ed25519", key, sig, canonBytes)`.

## Gate (deterministic, in code)

| Verdict | Rule flags that cause it | HTTP |
| :--- | :--- | :--- |
| `CLEAN_USER` | none: untainted session, no rule hit, insert only, at most 3 writes | 201, row in `memories` |
| `TAINTED_UNREVIEWED` | `tainted_session`, `write_burst` (4th+ write in a session), `overwrite_attempt` | 202 |
| `POLICY_BLOCKED` | `imperative_directive` (always, forward, ignore...), `external_email`, `external_url` (not on allowlist), `sensitive_tool` (send_email...), `canary_overlap`, `poison_similarity` (cosine to a purged row) | 202 |
| `INCONCLUSIVE` | `missing_provenance`, `invalid_schema`, `judge_failed` | 202 |

Precedence when several hit: `POLICY_BLOCKED` > `INCONCLUSIVE` > `TAINTED_UNREVIEWED`. All hit flags are recorded. The judge never upgrades a frozen row to `CLEAN_USER`; only a reviewer `override` promotes it, as `source='external_override'`.
