# State

Rewrite; do not append. Behaviour lives in SPECS.md, reasons in DECISIONS.md, sessions in history/. Budget 8 KB.

## Working
- Contracts 0.2.0 (D5): four verdicts, 13-flag x-rulebook, risk_score, demo endpoints; `check_contracts.py` passes including rulebook and sort checks. Change `refine-verdicts-and-rulebook` and 3 specs validate (strict).
- Infra local stack (pre-D5 schema): compose up, smoke_check 6/6.
- Backend skeleton (pre-D5 names): 77 offline tests + ruff pass; `/health`, `/keys/public`, auth, spoof 422, `/ui` mount.
- `POST /crawl` (D7, D8; contracts 0.2.1, change `add-crawl-endpoint`): host broker, public-target guard with DNS pinning, Docker runner, 2-run cap. 88 crawl tests pass locally (fake runner and fake resolver; 2 need Docker and skip without it, one of them a real container run); `docker inspect` of a run shows network none, read-only, CapDrop ALL, user 65534, no mounts. `infra/scripts/setup_crawl_sandbox.sh` is idempotent locally.
- Frontend shell (pre-D5 types): adapter-static at `/ui`, mock adapter, Web Crypto verification; `check:unified` passes.

## Not working or unverified
- Tracks still use the old verdict names. closed when: infra, backend and frontend Phase 1 tasks in [tasks.md](../../openspec/changes/refine-verdicts-and-rulebook/tasks.md) are done and each track check passes against fixtures 0.2.0.
- `infra/sql/001_init.sql` and the running local DB lack D5 columns. closed when: 001_init.sql mirrors contracts/schema.sql and smoke_check passes after re-apply.
- DB-backed endpoints return 501; session token checked for presence only. closed when: Gate 1 pytest hits local Postgres and a tainted write returns 202.
- Demo runner and sandbox egress test not built. closed when: `POST /demo/run` quarantined run reports leaked=false and `test_egress.py` passes.
- /crawl not live on the VM. closed when: tickets 07 (deploy `main`, Q9 key name) and 08 (live proof checklist, repeated by a second person) in `.scratch/add-crawl-endpoint/issues/` are done.
- /crawl latency against the 30 s limit unmeasured. closed when: ticket 08 records live latency; regular 504s open a contract change instead of a config edit.
- /crawl fetch is logged only, not recorded as `external_read`. closed when: Phase 1 DB repositories land and the broker fetch appends an audit event.
- Vultr resources (placeholders in vultr_provision.sh). closed when: Gate 2 `demo_smoke.py` passes on the live stack.

## Next
1. Phase 1 in parallel: infra, backend, frontend per the change tasks.
2. Archive `refine-verdicts-and-rulebook` once Gate 1 passes.
3. Apply `embedding-fail-closed` (new `embedding_unavailable` flag, contracts 0.3.0) after that archive.
