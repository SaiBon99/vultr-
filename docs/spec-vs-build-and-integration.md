# Spec vs build, and how the frontend and backend integrate

Status as of 2026-11-27 on branch `Agent_puke-Simon`.

Reference documents (the docs branch has priority):

- `origin/docs/plan-brief-idea`: `docs/Execution Plan.md` (the locked build plan), `docs/Project Idea.md` (same content as `spec.md`, reformatted), `docs/Hackathon Brief.md`.
- `spec.md` at the repo root: copy of *Project Idea*.

"Plan" below means *Execution Plan* unless marked otherwise.

Gap types: **Missing** (not built), **Changed** (built differently), **Extra** (built, not in plan), **Conflict** (the docs disagree).

---

## 1. Differences from the plan

### 1.1 Scope and scenario

| Area | Plan | Build | Type |
|---|---|---|---|
| Buyer scenario | B2B Sales / Deal Desk protecting floor pricing. Plan says "avoid purchasing, which Errand already covered" | Coffee purchasing assistant placing supplier orders (`place_order`, Roastery Co, `ALLOWED_DOMAINS=roastery-co.example`) | Changed |
| Pattern A (sandboxed code execution, `/tasks`) | Not mentioned | Built (`planner.py`, `runner.py`, `sandbox.py`, `frontend/index.html`) | Extra |
| Honeypot | Plan: deferred. *Project Idea*: in scope | Built (`honeypot.py`, `demo.py`) | Conflict |
| `eval.py` (10 attacks + 6 benign) | *Project Idea*: in scope. Plan: deferred | Not built | Conflict / Missing |
| `demo_smoke.py` containment check | Plan Gate 2 | Not built | Missing |

### 1.2 Deterministic gate

| Item | Plan | Build | Type |
|---|---|---|---|
| CLEAN_USER, TAINTED_UNREVIEWED, POLICY_BLOCKED, INCONCLUSIVE rules and priority | As written | Implemented in `gate.py`, 62 unit tests pass | Done |
| Judge failure after freeze → INCONCLUSIVE | Yes | Yes (`service.py`) | Done |
| Similarity to confirmed poison | pgvector cosine on `qwen3-embedding-4b` (1024 dims) | Word-shingle Jaccard over CRC32 fingerprints (documented deviation) | Changed |
| Missing session | INCONCLUSIVE, frozen in quarantine | 404, nothing stored | Changed |
| Invalid content (empty or malformed) | INCONCLUSIVE, frozen | 422 from Pydantic before the gate, nothing stored. Whitespace-only content reaches the gate and is frozen | Changed |
| Judge timeout | Fails closed | No explicit timeout. Falls back to the OpenAI client default | Missing |

### 1.3 Data model

| Table | Plan | Build | Type |
|---|---|---|---|
| `sessions` | `id`, `token_hash`, `gate_mode` (`quarantined`/`naive`), `external_sources`, `write_count`, `tainted` | `session_id` (16 hex), `label`, `gate_mode` (`gated`/`naive`), `namespace`, `tainted`, `write_count`. No `token_hash` | Changed |
| `memories` | `source` (`user`/`external_override`), `source_ref`, `payload_hash`, `embedding vector(1024)`, `promoted_from_quarantine_id` | `provenance` (`user`/`reviewed`/`unchecked`), `namespace`, `payload_hash`. No embedding, `source_ref`, or promotion link | Changed |
| `quarantine_queue` | `source`, `source_ref`, `verdict`, `rule_flags jsonb`, `judge_status`, `judge_note`, `override_reason`, `decided_by`, `decided_at`, `receipt_uri`, `embedding` | `verdict`, `flags TEXT[]`, `judge_note`, `status`, `override_reason`. Missing `source`, `source_ref`, `judge_status`, `decided_by/at`, `receipt_uri`, `embedding` | Missing |
| `audit_events` | `session_id`, `event_type`, `target_id`, `payload jsonb`, hashes | `event_type`, `payload` as text (deliberate, so hashes verify), hashes. No `session_id` or `target_id` | Changed |
| `reads` | Not in plan (`source_ref` on the row instead) | Present | Extra |
| `confirmed_poison` | Not in plan (embedding kept on purged row) | Present, holds the fingerprint | Changed |
| Postgres roles | `quarantine_proxy` (writer), `memory_reader` (SELECT on `memories` only), `GRANT USAGE ON SCHEMA public` | One DSN for the proxy. No roles | Missing |
| Schema source | `sql/001_init.sql` and `contracts/schema.sql` | Inline `SCHEMA` string in `store.py`, applied at startup | Changed |
| pgvector | `CREATE EXTENSION vector`, HNSW index | Not enabled, no `CREATE EXTENSION` anywhere | Missing |

### 1.4 Judge

| Item | Plan | Build | Type |
|---|---|---|---|
| Model | `qwen3.8-27b` (free fallback `qwen3.8-flash-next:free`) | Set by `VULTR_JUDGE_MODEL`. Recorded runs used `glm-5.3` as judge and `qwen3.8-27b` as worker, the reverse of the plan | Changed |
| Input | Session-bundled writes, provenance, rule flags. Never raw transcripts | One row: content, provenance, flags | Changed |
| Output schema | `summary`, `risk_level` (`low`/`medium`/`high`/`critical`), `recommended_action` (`purge`/`override`), `indicators` array | Exactly three keys. `risk_level` has no `critical`. `recommended_action` adds `review`. Any extra key, such as `indicators`, fails closed | Changed (incompatible) |
| Thinking output | `message.reasoning` | Not handled (only `message.content`) | Missing |

### 1.5 API surface

| Plan endpoint | Build | Type |
|---|---|---|
| `GET /health` (DB, Object Storage, Inference checks) | `GET /healthz` returns `{"ok": true}`, no checks | Changed |
| `POST /proxy/sessions` (`X-Host-Secret`) | Not exposed. Sessions are created in-process by trusted host code only | Changed (intentional) |
| `X-Session-Token` on sandbox calls | `session_id` in JSON body or query string | Changed |
| `POST /proxy/read` | Built | Done |
| `POST /proxy/memory/write` (201 active, 202 frozen) | Built | Done |
| `GET /proxy/memory/active` (pgvector ranking) | Built, but returns the last 50 rows by id in the namespace. No ranking | Changed |
| `GET /quarantine` (JSON, grouped by session, source snippets, receipt URIs) | Not built. `GET /ui` renders HTML | Missing |
| `POST /quarantine/{id}/decide` (JSON, signs receipt) | Not built as JSON. `POST /ui/rows/{id}/purge` and `/override` are form posts. No receipt | Changed / Missing |
| `GET /audit` with server-computed `chain_valid` | Returns rows. No `chain_valid` | Missing |
| `GET /keys/public` | Not built | Missing |
| `GET /receipts/{id}` | Not built | Missing |
| `X-Reviewer-Token` header | `X-Review-Token` header, or `?token=` in the URL. Reviewer token in the query string is a known risk | Changed |
| `DEMO_ALLOW_NAIVE=true` gate for naive mode | Not built. Naive mode is set in code and reachable through `POST /demo/runs` (review token required) | Missing |
| Routes not in plan | `POST /tasks`, `GET /tasks/{id}` (Pattern A), `GET /demo/runs`, `POST /demo/runs` | Extra |

### 1.6 Receipts and storage

| Item | Plan | Build | Type |
|---|---|---|---|
| Ed25519 signing | Canonical JSON, signed per event (`quarantined`/`purged`/`overridden`) | Not built. `cryptography` not in `requirements.txt` | Missing |
| Vultr Object Storage | Bucket `quarantine-receipts`, S3 keys, `https://<region>.vultrobjects.com`, `boto3` upload | Not built | Missing |
| Receipt schema | `contracts/receipt.schema.json` | Not in repo | Missing |

### 1.7 Frontend, infra, process

| Item | Plan | Build | Type |
|---|---|---|---|
| Review UI | SvelteKit 5, `adapter-static`, Ark UI, Acme tokens, session-grouped queue, raw source preview, judge JSON panel, audit viewer, Web Crypto receipt verifier | Server-rendered HTML string in `proxy.py`. Queue, purge, and override only | Missing (most of it) |
| Pattern A UI | Not in plan | One static HTML file (`frontend/index.html`) | Extra |
| Frontend tests | Vitest, Browser Mode, Playwright, axe | None | Missing |
| Local parity | `docker-compose.yml` (`pgvector/pgvector:pg16`, MinIO) | Not built | Missing |
| Scripts | `keygen_ed25519.py`, `setup_vultr_vx1.sh`, `vultr_provision.sh`, `smoke_check.py`, `reset_demo.py`, `demo_smoke.py` | Only `scripts/setup_vm.sh` (host setup, msb install, `msb doctor`) | Missing |
| Contracts | `contracts/schema.sql`, `openapi.yaml`, `receipt.schema.json`, `fixtures/` | Not in repo | Missing |
| Agent process files | `AGENTS.md` (root and scoped), `.agents/context/`, `openspec/` | Not in repo | Missing |
| Backend stack | Python 3.12, `uv`, `psycopg` v3, `pgvector`, `boto3`, `cryptography` | `pip`, `asyncpg`, `openai`, `microsandbox==0.8.3`. No `uv`, `psycopg`, `boto3`, `cryptography`, `pgvector` | Changed |
| Environment names | `HOST_SECRET`, `REVIEWER_TOKEN`, Object Storage keys | `REVIEW_TOKEN`. No `HOST_SECRET`. No storage keys | Changed |

### 1.8 Vultr-specific gaps

| Vultr item | Plan | Build | Status |
|---|---|---|---|
| VX1 VM, Ubuntu 24.04 | Single VM | Deployed, app under systemd | Done |
| Microsandbox on KVM | `msb doctor` green | Green on the VM; containment and egress tests pass there | Done |
| Managed PostgreSQL | Live, `sslmode=require` | Live. `DATABASE_URL` documented | Done |
| pgvector | Enabled, `vector(1024)`, HNSW | Not enabled | Missing |
| Object Storage | Bucket and S3 keys for receipts | Nothing | Missing |
| Serverless Inference: worker | Any live chat model | `qwen3.8-27b` | Done |
| Serverless Inference: judge | `qwen3.8-27b` | `glm-5.3` in recorded runs | Changed |
| Serverless Inference: embeddings | `qwen3-embedding-4b` | Not used. Model is live at `api.vultrinference.com/v1/models` | Missing |
| Public access | Plan silent on TLS | HTTP on `:8000`, no TLS, no firewall rules documented | Partial |
| Provisioning | `scripts/vultr_provision.sh` (Vultr API) | Manual console work, not scripted | Missing |
| Throwaway Vultr instances per task | Optional in brief | Not built. Microsandbox is the sandbox fabric | Optional |

### 1.9 Hackathon brief items

| Brief item | Build | Status |
|---|---|---|
| At least one execution pattern | Pattern A, `/tasks` | Done |
| Pattern A returns "real output (chart, file, test log)" | Returns stdout only | Partial |
| REST or WebSocket status and streaming (strongly recommended) | `GET /tasks/{id}` exists. No streaming. `/tasks` is synchronous | Partial |
| Web dashboard with execution loop and retries | Pattern A page shows attempts and stderr | Done for Pattern A |
| Approve-before-submit on irreversible browser action | Not applicable (no Pattern B). Review gate covers memory writes | N/A |
| Public demo URL | HTTP only | Partial |
| Recorded demo video with containment moment | Not done | Missing |
| `/tasks` access control | No auth. Anyone who reaches `:8000` can run model calls and sandboxes | Risk |

---

## 2. How the frontend and backend integrate

### 2.1 Current topology

```
Browser
 ├─ GET /                      frontend/index.html (Pattern A)
 │    ├─ POST /tasks           planner -> Serverless Inference -> Microsandbox -> retry loop
 │    └─ GET /tasks/{id}       in-memory _tasks dict
 │
 └─ GET /ui?token=...          HTML rendered in proxy.py
      ├─ POST /ui/rows/{id}/purge      form post, token in query
      └─ POST /ui/rows/{id}/override   form post, reason field

Sandbox (Microsandbox, egress to proxy only)
 └─ /proxy/read, /proxy/memory/write, /proxy/memory/active?session_id=

FastAPI (VX1)  ──► Managed PostgreSQL   (memories, quarantine_queue, audit_events, ...)
               ──► Serverless Inference (worker, judge)
               ──► Microsandbox         (per-run microVM)
```

The Pattern A page is static HTML that calls `/tasks`. The review UI is an HTML string built in Python. Neither has a build step, and neither has a JSON contract for the other side to rely on.

### 2.2 Target topology

```
Browser (SPA built from frontend/, adapter-static, same origin)
 ├─ /review, /review/{id}, /audit, /receipts/{id}, /demo, /     SvelteKit routes
 └─ /api/...                                                    JSON, X-Reviewer-Token header

FastAPI (VX1)
 ├─ /api/review/*   reviewer JSON (new module review_api.py)
 ├─ /api/keys/public
 ├─ /api/tasks*     Pattern A (existing, moved under /api, old /tasks kept during migration)
 ├─ /proxy/*        sandbox only (unchanged, session_id capability)
 ├─ /healthz
 └─ static: frontend/build with SPA fallback for every non-/api, non-/proxy path
```

Decisions this needs (see 2.8): whether to prefix JSON with `/api` (recommended, so SPA routes never collide with API routes), and whether to keep `/proxy/*` as the sandbox surface (recommended).

### 2.3 Screen to endpoint map

| Screen | Data needed | Target endpoint | Backend today | Change needed |
|---|---|---|---|---|
| Review queue | Frozen rows, grouped by session, with verdict, flags, judge summary | `GET /api/review/quarantine?status=quarantined` | `MemoryService.review_queue()` returns rows | Group by `session_id` in the response. Add `judge_status`, `source_ref` |
| Row detail | Content, source snippet, flags, judge JSON, receipt | `GET /api/review/quarantine/{id}` | `get_quarantine()` returns content, flags, judge note | Add source snippet: read `reads` by `session_id` and `source_ref`. Add `receipt_uri` |
| Purge | Action on one row | `POST /api/review/quarantine/{id}/decide` `{"action":"purge"}` | `MemoryService.purge()` | Sign and upload receipt. Return `receipt_uri` and audit head |
| Override | Action, typed reason for POLICY_BLOCKED | Same, `{"action":"override","reason":"..."}` | `MemoryService.override()` | Return 422 for missing reason. Keep 409 for already-decided |
| Judge panel | `summary`, `risk_level`, `recommended_action`, `indicators` | Inside row detail | Judge has 3 keys | Accept `indicators` and `critical` (see 2.5) |
| Audit viewer | Hash chain with validity flag | `GET /api/review/audit` | `store.list_audit()` returns rows | Add `verify_chain()` and return `chain_valid`. Paginate |
| Receipt verifier | Receipt JSON and signature, public key | `GET /api/review/receipts/{id}`, `GET /api/keys/public` | None | New `receipts.py` (Ed25519, boto3) |
| Demo runs | Results of naive and gated runs | `GET /api/review/demo-runs`, `POST /api/review/demo-runs` | `GET/POST /demo/runs` | Move under `/api`, keep response shape |
| Pattern A goal form | Goal, steps, output | `POST /api/tasks`, `GET /api/tasks/{id}`, later `GET /api/tasks/{id}/events` (SSE) | `POST /tasks`, `GET /tasks/{id}` | Move under `/api`. Add SSE by emitting from `TaskRunner` per attempt |
| Active memory panel (optional) | Active rows for a session | `GET /proxy/memory/active?session_id=` | Built | Browser holds a session_id only if the demo passes it. Decide before using (see 2.8) |

### 2.4 Auth

- **Reviewer.** One shared `REVIEW_TOKEN` today. The browser keeps it in `sessionStorage` after a login field, and sends it as `X-Reviewer-Token` on every `/api/review/*` call. Remove the `?token=` query parameter. It currently leaks into the URL, browser history, and server logs.
- **CSRF.** Header-based auth with no cookies means a cross-site form cannot send the token, so the form-post routes can be replaced by `fetch` calls without adding CSRF tokens.
- **Same origin.** Serve the SPA and the API from the same FastAPI process. No CORS configuration is needed. For local development, use a Vite proxy to `uvicorn` on `:8000`.
- **Sandbox.** Keep `session_id` for now. It is a capability for one session and is documented as such. Move to host-minted `X-Session-Token` only if the plan's requirement is kept.
- **Status codes.** `503` when `REVIEW_TOKEN` is unset, `401` for a missing or wrong token (both already exist in `proxy.py`).

### 2.5 Backend changes, in order

1. **Review JSON module.** New `backend/app/memory/review_api.py`, mounted under `/api/review`. Reuses `MemoryService` methods. Keep `/ui` during migration, then remove it.
2. **Pydantic response models.** Export `openapi.yaml` from FastAPI and check it into `contracts/`. Use the same file as the frontend's type source.
3. **Schema changes.** Add `source`, `source_ref`, `judge_status`, `decided_by`, `decided_at`, `receipt_uri` to `quarantine_queue`. Rename `flags` to `rule_flags` (JSONB) if the plan's schema is kept. Move the schema into `sql/001_init.sql`.
4. **pgvector.** `CREATE EXTENSION vector`, add `embedding vector(1024)` to `quarantine_queue` and `memories`, call `qwen3-embedding-4b` in `write()` for the poison check, keep the shingle check as a fallback.
5. **Roles.** Create `quarantine_proxy` (writer) and `memory_reader` (SELECT on `memories` only). Point `/proxy/memory/active` at the reader pool.
6. **Judge.** Accept `indicators` (list of strings) and `critical`. Add an explicit timeout (for example 20 s) so a hang fails closed. Keep `review` as an allowed action only if the UI uses it.
7. **Errors.** Split `ReviewError` into "already decided" (409) and "reason required" (422). Map missing session and invalid content to INCONCLUSIVE rows, or keep 404/422 and document the change.
8. **Audit.** Add `verify_chain()` that recomputes every hash from stored rows, and return `chain_valid`. Add `session_id` and `target_id` columns.
9. **Receipts.** New `backend/app/memory/receipts.py`. Canonical JSON (sorted keys, compact), Ed25519 sign with `cryptography`, upload with `boto3` to the `quarantine-receipts` bucket, store `receipt_uri`. Expose `GET /api/keys/public` (base64 and JWK).
10. **Static serving.** Mount `frontend/build` at `/` after all API routes, with an SPA fallback to `index.html` for unknown non-API paths.
11. **Pattern A streaming.** Give `TaskRunner.run()` an optional async callback that receives each attempt, and expose it as SSE. Keep `GET /api/tasks/{id}` for polling.

### 2.6 Frontend build

- **Stack (from the plan):** SvelteKit 5 with `adapter-static`, Tailwind v4, Ark UI, Acme tokens from `acme.zip`, Vitest, Playwright. Icons and motion as the plan lists.
- **Layout.** `frontend/src/routes/review/+page.svelte` (queue), `review/[id]/+page.svelte` (detail with purge and override), `audit/+page.svelte`, `receipts/[id]/+page.svelte` (verifier), `demo/+page.svelte`, and `/` for Pattern A.
- **Data layer.** One typed client generated from `contracts/openapi.yaml`. A mock adapter reads `contracts/fixtures/`, chosen by `VITE_API_MODE=mock|live`. This lets the frontend start before the backend is finished (the plan's phase 1 parallel tracks).
- **Verification in the browser.** Web Crypto `Ed25519` verifies the receipt signature against `GET /api/keys/public`. Canonical JSON must be byte-identical to the backend's (same key order, same separators), so store the canonicalisation rule in `contracts/receipt.schema.json`.
- **Build and deploy.** `pnpm build` writes `frontend/build`. The deploy step copies it to the VM under the app directory. FastAPI serves it. No separate frontend server.
- **Current Pattern A page.** Can stay as `frontend/index.html` until the SPA exists, as long as its `/tasks` calls are kept or updated in the same change.

### 2.7 Sequence: purge with receipt

1. UI sends `POST /api/review/quarantine/42/decide` with `{"action":"purge"}` and `X-Reviewer-Token`.
2. Route checks the token. Unknown token returns 401, unset `REVIEW_TOKEN` returns 503.
3. `MemoryService.purge(42)` fingerprints the content, then `store.purge_quarantine()` wipes `content`, sets `status='purged'`, and inserts the fingerprint into `confirmed_poison` in one transaction.
4. `audit.append("purge", ...)` appends to the hash chain.
5. `receipts.sign_and_upload(event="purged", ...)` signs the canonical JSON and writes it to Object Storage, then stores `receipt_uri` on the row.
6. Response `200` with `{"status":"purged","receipt_uri":"...","audit_head":"..."}`.
7. UI refreshes the queue. The verifier page fetches `GET /api/review/receipts/42`, fetches `GET /api/keys/public`, and verifies in Web Crypto.

Ordering matters at step 5. If the upload fails after the purge commits, the row is purged with no receipt. Either upload first and then commit, or record `receipt_status='pending'` and retry. Pick one before building.

### 2.8 Open decisions

1. **Path prefix.** `/api/...` (recommended, avoids collisions with SPA routes) or the plan's unprefixed `/quarantine/...`.
2. **Buyer scenario.** Keep coffee purchasing (the current demo) or change to the plan's Deal Desk floor pricing. The plan says to avoid purchasing.
3. **Pattern A.** Keep it as an extra or drop it to focus on the memory product.
4. **Sandbox capability.** Keep `session_id` or implement `X-Session-Token` as the plan says.
5. **Judge schema.** Adopt the plan's schema (`indicators`, `critical`) or keep the three-key schema and update the plan.
6. **TLS.** Terminate TLS on the VM (reverse proxy with a certificate) or use a Vultr load balancer with TLS. Required before a reviewer token is used on a public URL.
7. **Eval.** Build `eval.py` (per *Project Idea*) or defer it (per *Execution Plan*).

---

## 3. Source pointers

- Routes: `backend/app/main.py`, `backend/app/memory/proxy.py`
- Service logic: `backend/app/memory/service.py`
- Gate: `backend/app/memory/gate.py`
- Storage and audit: `backend/app/memory/store.py`
- Judge: `backend/app/memory/judge.py`
- Demo and honeypot: `backend/app/memory/demo.py`, `backend/app/memory/honeypot.py`, `backend/app/memory/worker.py`
- Sandbox and Pattern A: `backend/app/sandbox.py`, `backend/app/planner.py`, `backend/app/runner.py`
- Settings: `backend/app/config.py`, `.env.example`
- Pattern A UI: `frontend/index.html`
- Host setup: `scripts/setup_vm.sh`
- Tests: `tests/` (62 unit tests, 7 `integration` tests that need KVM)
