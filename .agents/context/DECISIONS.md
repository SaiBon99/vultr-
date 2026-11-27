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
| D5 | Chainguard MinIO images locally | active |

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

## D5: Chainguard MinIO images locally

Local S3 uses `chainguard/minio` and `chainguard/minio-client`; production uses Vultr Object Storage.
- Why: official MinIO images could not be pulled (denied / 401) on 2026-11-27.
- Revisit if: the official images become pullable or Chainguard tags stop being free.
