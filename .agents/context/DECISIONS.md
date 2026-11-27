# Decisions

One entry per change of direction, newest last, at most 8 lines. Never rewrite an entry: add one that supersedes it and set the old status to "superseded by Dn".
A superseding entry adds `- Context changed:`; one whose reason can expire (a price, a provider, a guess) adds `- Revisit if:`.

## Index

| ID | Decision | Status |
| :--- | :--- | :--- |
| D1 | Frontend stack | active |
| D2 | Option B storage, vector(1024) | active |
| D3 | One root record; tracks own folders | active |
| D4 | Wire rules for hashing and signing | active |
| D5 | Four verdicts, 13-flag rulebook, risk_score | active |
| D6 | Chainguard MinIO images locally | active |
| D7 | Docker sandbox and host broker for /crawl | active |
| D8 | /crawl runs at most 2 at once; 503 sandbox_busy | active |
| D9 | Run logs share the receipts bucket under logs/ | active |
| D10 | Chat agent: 90 s, 8 tools a message; checkout simulated | active |

## D1: Frontend stack

Chosen with sk-init on 2026-11-27 from the Execution Plan: SvelteKit (Svelte 5), pnpm, Tailwind CSS v4, Ark UI, ESLint 10 + Prettier, Terrazzo tokens, Geist fonts, Lucide, Vitest + Playwright.
- Why: locked in the plan; adapter-static output is served by FastAPI, so no separate frontend server.
- Revisit if: a major version of a core package ships.

## D2: Option B storage, vector(1024)

Separate `memories` (active) and `quarantine_queue` tables; `memory_reader` role sees only `memories`. Purge nulls content, keeps payload_hash and embedding.
- Why: filtered HNSW on one table drops recall, and every read path would have to remember the status filter.

## D3: One root record; tracks own folders

`.agents/context/`, `openspec/`, `CODE.md` live at the root (hoisted from the sk-init frontend scaffold). infra/, backend/, frontend/ each have a scoped AGENTS.md and write only inside their folder.
- Why: three agents run in parallel with zero merge conflicts and no duplicate state files.

## D4: Wire rules for hashing and signing

Canonical JSON = sorted keys, compact, UTF-8; audit hash = sha256(prev_hash + "|" + canon(body)) excluding seq; receipts add `key_id` (beyond the plan's example) so the browser can match the key.
- Why: Python and the browser must produce identical bytes; fixtures are cross-checked in both languages.

## D5: Four verdicts, 13-flag rulebook, risk_score

Verdicts ALLOW / NEEDS_REVIEW / BLOCKED / FAIL_CLOSED (FAIL_CLOSED first), 13 flags with weights in x-rulebook, integer risk_score (FAIL_CLOSED floor 85), Stage 0 hidden-character stripping, +15 judge sort boost, demo runner endpoints. Change: openspec/changes/refine-verdicts-and-rulebook.
- Why: broken provenance must outrank policy hits; reviewers need a deterministic order; the judge may raise priority but never decide ([Execution Plan, threat model](../../docs/Execution%20Plan.md#threat-model-and-detection)).
- Context changed: supersedes the D4-era verdict names; D6 was renumbered from D5 to make room.
- Revisit if: eval.py shows tainted-session escapes or benign false blocks.

## D6: Chainguard MinIO images locally

Local S3 uses `chainguard/minio` and `chainguard/minio-client`; production uses Vultr Object Storage.
- Why: official MinIO images could not be pulled (denied / 401) on 2026-11-27.
- Revisit if: the official images become pullable or Chainguard tags stop being free.

## D7: Docker sandbox and host broker for /crawl

`POST /crawl` runs its agent in one fresh Docker container per request (`--network none`, read-only root, non-root, no capabilities, no env, no mounts, SANDBOX_* caps), not Microsandbox. The host does the page fetch and the model call and answers the agent over stdin and stdout; the inference key never enters the container. Change: openspec/changes/add-crawl-endpoint.
- Why: Docker is already on the VM and the Execution Plan allows it as the fallback; with no network the host broker is the only way out, so egress control is not needed inside the sandbox. Departs from the plan's Microsandbox-first design for this endpoint only; `/demo/run` is unchanged.
- Revisit if: `msb doctor` is green on the VX1 and the demo needs Microsandbox's egress control.

## D8: /crawl runs at most 2 at once; 503 sandbox_busy

A third concurrent `/crawl` request gets 503 with code `sandbox_busy` immediately, before any container starts. No queue.
- Why: each run reserves up to 512 MB and 1 CPU on an 8 GB VM; rejecting keeps both memory and latency bounded.
- Revisit if: the VM size changes or reviewers routinely hit `sandbox_busy`.

## D9: Run logs share the receipts bucket under logs/

Each /crawl run writes one redacted NDJSON transcript to `S3_BUCKET` at `logs/crawl/<run_id>.jsonl` (sessions reserved at `logs/sessions/<session_id>/`), next to `receipts/`. Change: openspec/changes/add-run-logs; wire rule 6.
- Why: one Object Storage subscription and one credential pair; the optional expiry rule (`setup_object_storage.py --logs-expire-days`) filters on `logs/` only, so receipts never expire.
- Revisit if: logs need a different retention, access policy or region from receipts, or Vultr rejects prefix-scoped lifecycle rules.

## D10: Chat agent: 90 s, 8 tools a message; checkout simulated

`/chat` replaces the Crawl tab: one Docker sandbox per message (D7 isolation, D8 cap shared), host-brokered tools, SSE steps. A message runs at most `CHAT_TIMEOUT_S` (90) and `CHAT_MAX_STEPS` (8); memory and CPU caps stay at the SANDBOX_* values. `place_order` is always simulated and `send_email` always refused. Change: openspec/changes/add-chat-agent.
- Why: a multi-step tool loop needs several model calls, which do not fit 30 s; simulated checkout lets the agent browse any public URL with no purchase risk.
- Revisit if: median message time stays under 30 s, or the demo needs a real checkout.
