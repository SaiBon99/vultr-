# State

Rewrite; do not append. Behaviour lives in SPECS.md, reasons in DECISIONS.md, sessions in history/. Budget 8 KB.

## Working
- Contracts frozen (Phase 0): [contracts/README.md](../../contracts/README.md); `check_contracts.py` passes; 3 OpenSpec specs validate.
- Infra local stack: pgvector PG16 + MinIO via `infra/docker-compose.yml`; `infra/scripts/smoke_check.py` 6/6; local signing key in `infra/keys/` (git-ignored).
- Backend skeleton: 76 offline tests + ruff pass. Live: `/health`, `/keys/public`, `/receipts/{id}`, auth 401s, spoofed `source` 422, `/ui` static mount. Verified against local DB and MinIO via `backend/scripts/serve.py`.
- Frontend shell: adapter-static at base `/ui`, typed client from openapi.yaml, mock adapter on contracts/fixtures, Web Crypto receipt and audit-chain verification (6 Vitest), Playwright smoke 2/2; `check:unified` passes.

## Not working or unverified
- DB-backed endpoints (`/proxy/sessions`, `/proxy/read`, `/proxy/memory/*`, `/quarantine*`, `/audit`) return 501. closed when: Gate 1 pytest hits local Postgres and a tainted write returns 202.
- Session token checked for presence only. closed when: token hash looked up in `sessions`.
- Review UI badges render as plain text; Purge/Override, receipt viewer and token entry not built. closed when: Phase 1 frontend done check passes.
- Acme tokens mapping into `frontend/tokens/` not reviewed (brand colour confirmed). closed when: tokens diffed against `frontend/acme/tokens.json`.
- `JUDGE_MODEL_FALLBACK` missing from backend config; `S3_REGION` missing from `infra/.env.example`. closed when: both present.
- Vultr resources and `vultr_provision.sh` flags (placeholders). closed when: Gate 2 `demo_smoke.py` passes on the live stack.

## Next
1. Phase 1 in parallel per [docs/Execution Plan.md](../../docs/Execution%20Plan.md): backend repo layer + routes on local Postgres; frontend Review UI actions; infra Vultr scripts.
2. Gate 1 checks.
