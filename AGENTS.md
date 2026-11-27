# Memory Quarantine for AI Agents

Host-side Memory Proxy that gates every agent memory write by session provenance, freezes tainted writes in quarantine, has an isolated judge explain them, and waits for a human Purge or Override with signed receipts. Built for the Vultr Agent Runtime Hackathon ([brief](docs/Hackathon%20Brief.md), [idea](docs/Project%20Idea.md), [plan](docs/Execution%20Plan.md)).

## Layout and ownership
| Dir | Owner | Stack | Scoped rules |
| :--- | :--- | :--- | :--- |
| `/`, `contracts/`, `.agents/`, `openspec/` | Coordinator | Record, OpenSpec, frozen contracts | this file |
| `infra/` | Infra agent | Docker Compose (pgvector PG16, MinIO), SQL, Vultr scripts | [infra/AGENTS.md](infra/AGENTS.md) |
| `backend/` | Backend agent | Python 3.12, uv, FastAPI, psycopg 3, pgvector, openai SDK, boto3, cryptography | [backend/AGENTS.md](backend/AGENTS.md) |
| `frontend/` | Frontend agent | SvelteKit 5, pnpm, adapter-static, Ark UI, Tailwind v4, Acme tokens | [frontend/AGENTS.md](frontend/AGENTS.md) |

Each track writes only inside its own folder. `contracts/` is read-only for tracks; propose changes in `openspec/changes/`.

## Commands
```bash
uv run --no-project --with jsonschema --with pyyaml --with cryptography python contracts/check_contracts.py  # contracts
docker compose -f infra/docker-compose.yml up -d        # local Postgres + MinIO
cd backend && uv run pytest                              # backend
cd frontend && pnpm run check:unified                    # frontend
node .agents/skills/close-session/record_check.mjs       # record budgets and links
```

## Invariants
1. The sandbox holds no DB, S3 or LLM credentials and has no direct egress to Postgres (5432), Object Storage (9000) or the internet; it runs capped at 512 MB, 1 CPU and 30 s (90 s a chat message, D10) and is destroyed after each run. Everything goes through `/proxy/*`. `session_id` and `source` are derived server-side from `X-Session-Token`; request bodies never carry them.
2. Recall reads `memories` only, through the `memory_reader` role. Quarantined rows never reach an agent.
3. Code decides the verdict (`ALLOW`, `NEEDS_REVIEW`, `BLOCKED`, `FAIL_CLOSED`) and the `risk_score`; `backend/app/gate.py` stays pure. The judge only explains or raises review priority; judge failure escalates `NEEDS_REVIEW` to `FAIL_CLOSED` and never downgrades.
4. `audit_events` is append-only. Hashing, canonical JSON and receipt signing follow [contracts/README.md](contracts/README.md) exactly.
5. Never read, print or commit `.env*`, private keys or tokens. Ask before destructive actions.

## Read first
1. [STATE.md](.agents/context/STATE.md): now; every unverified item says `closed when:`.
2. [LEARNINGS.md](.agents/context/LEARNINGS.md): gotchas; search before debugging.
3. [DECISIONS.md](.agents/context/DECISIONS.md): grep the Index; open an entry for its reasons.
On demand: [SPECS.md](.agents/context/SPECS.md) for what a capability does (openspec/specs/). End a session with the close-session skill.

## Read when
| Task | File |
| :--- | :--- |
| Any API, DB or receipt work | [contracts/README.md](contracts/README.md), [contracts/openapi.yaml](contracts/openapi.yaml) |
| Gate rules, flags, risk_score | [Threat model and detection](docs/Execution%20Plan.md#threat-model-and-detection), `x-rulebook` in [contracts/openapi.yaml](contracts/openapi.yaml) |
| Changing structure | [ARCHITECTURE.md](.agents/context/ARCHITECTURE.md) |
| UI or styling | [UI.md](.agents/context/UI.md), [frontend/DESIGN.md](frontend/DESIGN.md) |
| Coding standards | [CODE.md](CODE.md) |
| Frontend stack and versions | [STACK.md](.agents/context/STACK.md) |
