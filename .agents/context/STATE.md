# State

Rewrite; do not append. Behaviour lives in SPECS.md, reasons in DECISIONS.md, sessions in history/. Budget 8 KB.

## Working
- Contracts 0.2.0 (D5): four verdicts, 13-flag x-rulebook, risk_score, demo endpoints; `check_contracts.py` passes including rulebook and sort checks. Change `refine-verdicts-and-rulebook` and 3 specs validate (strict).
- Infra local stack (pre-D5 schema): compose up, smoke_check 6/6.
- Backend skeleton (pre-D5 names): 77 offline tests + ruff pass; `/health`, `/keys/public`, auth, spoof 422, `/ui` mount.
- `POST /crawl` (D7, D8; contracts 0.2.1, change `add-crawl-endpoint`): host broker, public-target guard with DNS pinning, Docker runner, 2-run cap. 88 crawl tests pass locally (fake runner and fake resolver; 2 need Docker and skip without it, one of them a real container run); `docker inspect` of a run shows network none, read-only, CapDrop ALL, user 65534, no mounts. `infra/scripts/setup_crawl_sandbox.sh` is idempotent locally.
- /crawl live on the VM (ticket 07, 2026-11-27): `main` @ 4ee066e as `quarantine-api.service` at `http://45.77.138.3:8000`; old `vultr-app` disabled, kept for rollback. One run against example.com: 200 in 2.1 s, network none, container removed.
- Frontend `/crawl` page and live build (ticket 09): same-origin `/ui`, verdict names moved to contracts 0.2.1. CI workflow `deploy.yml` publishes on push to `main` via `infra/scripts/publish.sh`, rolls back on failed checks.
- Run logs (D9; contracts 0.2.2, change `add-run-logs`, tickets 01-16 in `.scratch/add-run-logs/issues/`): every /crawl run that took a slot writes a redacted, capped NDJSON transcript to `logs/crawl/<run_id>.jsonl`; 502/504 carry `run_id`; `GET /crawl/runs/{run_id}/log` (reviewer); `/ui/crawl` viewer. 24 tests in `test_crawl_runlog.py`. Local e2e 2026-11-27 against MinIO and the real Docker sandbox: smoke_check 7/7 incl. logs probe; example.com 200 with log_uri, sha256 metadata matches GET bytes, no secrets in the object; a 404 page gives 502 fetch_failed with run_id and an error run_end; MinIO stopped gives 200 `log_uri: null` and one warning line. `setup_object_storage.py` idempotent on MinIO.
- Run logs live on Vultr (ticket 17, 2026-11-27, `98e8f43` via publish.sh): Object Storage `quarantine-objects` on ams1 (cluster 6, Standard tier, $18/mo; VM is in ams), bucket `quarantine-receipts`, path style, `S3_REGION=ams1`; S3_* in `/opt/vultr-app/.env` (600, runner). setup_object_storage.py passed twice on the live bucket (second run: no changes); only lifecycle rule is `expire-run-logs` on `logs/`, 30 days. /health object_storage ok; a real crawl of example.com (real inference, 2.5 s) wrote `logs/crawl/<run_id>.jsonl`, GET log 200 with sha256 matching the bucket metadata, no secrets in the object.
- Frontend shell (pre-D5 types): adapter-static at `/ui`, mock adapter, Web Crypto verification; `check:unified` passes.

- Chat agent contract (D10; contracts 0.2.3, change `add-chat-agent`): `/chat/*` paths, Chat* schemas, `chat_stream.json` fixture; check_contracts validates it.

## Not working or unverified
- Chat agent backend and `/ui/chat` not built. closed when: tasks 2-4 in [tasks.md](../../openspec/changes/add-chat-agent/tasks.md) are checked and one live message orders from a public page with the injected note quarantined.
- Tracks still use the old verdict names. closed when: infra, backend and frontend Phase 1 tasks in [tasks.md](../../openspec/changes/refine-verdicts-and-rulebook/tasks.md) are done and each track check passes against fixtures 0.2.0.
- `infra/sql/001_init.sql` and the running local DB lack D5 columns. closed when: 001_init.sql mirrors contracts/schema.sql and smoke_check passes after re-apply.
- DB-backed endpoints return 501; session token checked for presence only. closed when: Gate 1 pytest hits local Postgres and a tainted write returns 202.
- Demo runner and sandbox egress test not built. closed when: `POST /demo/run` quarantined run reports leaked=false and `test_egress.py` passes.
- /crawl live proof not done. closed when: ticket 08 (checklist written, `docker inspect` mid-run, journal line, Vultr usage, repeated by a second person) in `.scratch/add-crawl-endpoint/issues/` is done.
- /crawl latency measured once (2.1 s, example.com). closed when: ticket 08 records latency across several runs; regular 504s open a contract change instead of a config edit.
- /crawl fetch is logged only, not recorded as `external_read`. closed when: Phase 1 DB repositories land and the broker fetch appends an audit event.
- Live `/ui/crawl` run-log viewer not looked at in a browser. closed when: a reviewer opens a crawl's run log on http://45.77.138.3:8000/ui/crawl/ and it renders.
- `98e8f43` was pushed with `[skip ci]` and deployed by hand, so CI has not run on it. closed when: the next CI run on main passes.
- Vultr resources (Object Storage cluster lookup is real; other placeholders in vultr_provision.sh). closed when: Gate 2 `demo_smoke.py` passes on the live stack.

## Next
1. Phase 1 in parallel: infra, backend, frontend per the change tasks.
2. Archive `refine-verdicts-and-rulebook` once Gate 1 passes.
3. Apply `embedding-fail-closed` (new `embedding_unavailable` flag, contracts 0.3.0) after that archive.
4. Archive `add-run-logs` once the live viewer is confirmed.
