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

1. **Canonical JSON**: keys sorted by code point at every depth, separators `,` and `:` with no whitespace, UTF-8, non-ASCII unescaped, no floats, integers within ±(2^53−1), no lone surrogates. Python: `json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. JS: see `canon()` in [fixtures/generate.mjs](fixtures/generate.mjs).
2. **payload_hash**: `"sha256:" + hex(sha256(utf8(content)))`, content exactly as written (no trimming or normalization).
3. **Audit chain**: genesis `prev_hash = "sha256:" + "0"*64`. `event_hash = "sha256:" + hex(sha256(utf8(prev_hash + "|" + canon({session_id, event_type, target_id, payload, created_at}))))`. `seq` is not hashed. `prev_hash` is unique, so the chain cannot fork; `head_hash` in `GET /audit` is the stored `event_hash` of the last row, valid or not. `created_at` is the string `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC, microseconds); the backend formats it once, stores it, and returns that exact string.
4. **Receipt signature**: Ed25519 over `utf8(canon(receipt without signature_b64))`; `signature_b64` is standard base64. `key_id` = first 16 hex chars of sha256(raw 32-byte public key). `audit_head_hash` = `event_hash` of the newest audit row before the `receipt_signed` event. Stored at `s3://quarantine-receipts/receipts/<receipt_id>.json`.
5. **Browser verification**: `crypto.subtle.importKey("jwk", jwk, {name: "Ed25519"}, false, ["verify"])`, then `verify("Ed25519", key, sig, canonBytes)`.
6. **Run log** (0.2.2, [design](../openspec/changes/add-run-logs/design.md#object-layout-and-line-format)): one NDJSON object per run that took a sandbox slot, in the receipts bucket. Key `logs/crawl/<run_id>.jsonl` (sessionless runs) or `logs/sessions/<session_id>/<run_id>.jsonl` (reserved). Lines are `json.dumps(line, ensure_ascii=False)` plus `\n` (not canonical). Types: `run_start` (first: run_id, kind, session_id, started_at, limits, image_id), `msg` (seq, t_ms, dir `host_to_agent` or `agent_to_host`, then `msg` for a parsed line or `raw` for an unparseable agent line, at most 4 KB, invalid UTF-8 replaced), `host` (seq, t_ms, event `fetch` or `model`; never a prompt), `run_end` (last: status `ok` or `error`, http_status, error_code, exit_code, container_id, elapsed_ms, stderr, stderr_truncated, lines_dropped). `seq` counts up across `msg` and `host`; `t_ms` is milliseconds since `run_start`. Order: replace every configured secret of 8+ chars (raw and JSON-escaped) with `[REDACTED]`, then cut, then hash, so no cut leaves a fragment of a secret. Caps (UTF-8 bytes, never splitting a character): `fetch_result.body` and `model.page_text` over 16 KB keep their first 16 KB plus `<field>_truncated: true`, `<field>_chars` (character length of the full redacted text) and `<field>_sha256` (hex of the full redacted UTF-8 text); `fetch_result` always carries `body_truncated`; `raw` 4 KB; stderr 64 KB; object 1 MB, with `run_start` and `run_end` always kept and later `msg`/`host` lines counted in `lines_dropped`. Put with `Content-Type: application/x-ndjson` and metadata `sha256` = hex(sha256(stored bytes)), `kind`, `session-id`.

## Stage 0 (inspection copy)

`payload_hash` and storage always use the raw bytes. The rules run on a copy with these removed: zero-width U+200B to U+200F, U+2060, U+FEFF; tag characters U+E0000 to U+E007F; bidi controls U+202A to U+202E and U+2066 to U+2069.

## Gate (deterministic, pure code in `backend/app/gate.py`)

Machine-readable source of truth: `x-rulebook` on `RuleFlag` in [openapi.yaml](openapi.yaml). Precedence: `FAIL_CLOSED` > `BLOCKED` > `NEEDS_REVIEW` > `ALLOW`; every hit flag is recorded.

| Verdict | Flags (weight) | HTTP | Override |
| :--- | :--- | :--- | :--- |
| `FAIL_CLOSED` | `missing_provenance`, `invalid_schema`, `judge_failed` (score floor 85) | 202 | reason required |
| `BLOCKED` | `imperative_directive` (40), `external_email` (45), `external_url` (45), `sensitive_tool` (45), `canary_overlap` (90), `poison_similarity` (90) | 202 | reason required |
| `NEEDS_REVIEW` | `tainted_session` (25), `immediate_write_after_read` (10), `write_burst` (15), `overwrite_attempt` (25) | 202 | reason optional |
| `ALLOW` | none: untainted, insert-only, at most 3 writes | 201, row in `memories` | n/a |

- **risk_score** = `min(100, sum of weights)`; `0` for `ALLOW`; `max(85, ...)` for `FAIL_CLOSED`. Set by code at freeze; the judge never changes it.
- **immediate_write_after_read**: session tainted and `writes_since_last_read == 0` at write time.
- **write_burst**: the 4th and later write in a session.
- **external_email / external_url**: host not equal to, or a strict subdomain of, an entry in `ALLOWLISTED_DOMAINS`. The host comes from a real URL parse, so userinfo (`https://good.com@evil.com`) cannot spoof it. IP literals and unparseable URLs count as external.
- **imperative_directive**: an imperative or conditional directive aimed at an outbound action, recipient, tool or policy override (`always/when/before ... forward/send/cc/bcc/post`, `ignore/bypass previous instructions/limits`). Plain preferences (`customer always prefers net-30`) do not fire.
- **poison_similarity**: cosine similarity to a purged tombstone embedding at or above `POISON_SIMILARITY_THRESHOLD` (0.85). Tombstones are never pre-seeded from `eval.py`.

## Judge failure and review order

- Judge timeout or invalid JSON: `judge_status = failed`, `judge_failed` is appended to `rule_flags`, and an audit `judge_failed` event records `{error, previous_verdict, new_verdict}`. `NEEDS_REVIEW` escalates to `FAIL_CLOSED` with `risk_score = max(risk_score, 85)`; `BLOCKED` keeps its verdict and score.
- `effective_priority_score = risk_score + 15` when `judge_note.recommended_action == "purge"` and `risk_level` is `high` or `critical`. `GET /quarantine` sorts items by `(effective_priority_score DESC, created_at DESC)` and sessions by their top item.
- Models never promote or downgrade. Only a reviewer `override` promotes, after `sha256(utf8(content)) == payload_hash`, as `source='external_override'`. Receipts (`purged` or `overridden`) are signed only at that decision.
