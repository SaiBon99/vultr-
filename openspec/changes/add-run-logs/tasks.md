## 1. Contracts (Coordinator)
- [x] 1.1 openapi.yaml 0.2.2: `CrawlResult.run_id`, `CrawlResult.log_uri`, optional `Error.run_id`, path `GET /crawl/runs/{run_id}/log` (200 x-ndjson, 401, 404, 503)
- [x] 1.2 README.md wire rule 6: run-log layout, line types, caps, redact-then-hash, `sha256` metadata
- [x] 1.3 Fixtures and check_contracts.py updated if they cover CrawlResult or Error; contracts check passes
- [x] 1.4 DECISIONS D9 (run logs share the receipts bucket under logs/)

## 2. Infra
- [x] 2.1 scripts/setup_object_storage.py: bucket create-if-missing, private check, optional lifecycle on `logs/` only, probe round trip, idempotent, no secrets printed
- [x] 2.2 scripts/smoke_check.py: `S3_REGION` from env; logs/ put-get-delete check
- [x] 2.3 scripts/vultr_provision.sh: real cluster lookup by region (flags checked against `vultr-cli object-storage --help`), dry-run default
- [x] 2.4 .env.example notes (shared bucket, unique bucket names, `S3_REGION` = cluster id, optional `S3_LOGS_EXPIRE_DAYS`); README.md and AGENTS.md list the script

## 3. Backend
- [x] 3.1 app/storage.py: store classes moved from receipts.py (re-exported), `put_bytes` with metadata, `head`, botocore timeouts, path style, s3v4; in-memory fake with metadata and `fail`
- [x] 3.2 app/runlog.py: RunLog lines, truncation, 1 MB cap with `lines_dropped`, redaction, `run_log_key`, best-effort `upload_run_log`; `Settings.log_secrets`
- [x] 3.3 app/crawl/runner.py: stderr PIPE drained concurrently, 64 KB cap, `stderr_text()`, cleanup cancels the drain; argv unchanged
- [x] 3.4 app/crawl/service.py: run_id after slot taken, broker records every line and host events, finish and upload in `finally`, `run_id` and `log_uri` on success, `run_id` on CrawlError
- [x] 3.5 Error handler adds `run_id`; models.py fields
- [x] 3.6 app/routes/crawl.py: pass the store to crawl(); `GET /crawl/runs/{run_id}/log`
- [x] 3.7 tests/test_crawl_runlog.py: every case listed in design.md §Backend 8
- [x] 3.8 `uv run pytest -q` and `uv run ruff check` on the scoped list pass

## 4. Frontend
- [x] 4.1 schema.d.ts regenerated from 0.2.2
- [x] 4.2 client.ts and mock.ts `getCrawlRunLog`
- [x] 4.3 /crawl page shows run_id and the run-log viewer for success and error
- [x] 4.4 `pnpm run check:unified` and e2e smoke pass

## 5. CI and record
- [x] 5.1 deploy.yml scoped ruff list includes the new and changed backend files
- [x] 5.2 STATE.md and LEARNINGS.md updated; `record_check.mjs` passes

## 6. Live hookup (admin, keys)
- [x] 6.1 VM region found; Object Storage region chosen and recorded
- [x] 6.2 Subscription created after user confirmation (billable)
- [x] 6.3 Live EnvironmentFile found via `systemctl cat quarantine-api`; S3_* set, mode 600, nothing echoed
- [x] 6.4 setup_object_storage.py passes twice (second run: no changes), lifecycle `logs/` 30 days or warning recorded
- [x] 6.5 Change deployed to the VM (CI on main or publish.sh); service restarted

## 7. Verification
- [x] 7.1 Local: compose up; smoke_check passes including the logs probe. Expected: all PASS
- [x] 7.2 Local: POST /crawl example.com with MinIO. Expected: 200 with `log_uri`; GET log returns NDJSON whose sha256 equals the object metadata
- [x] 7.3 Local: grep the object for the reviewer token and inference key. Expected: no match
- [x] 7.4 Local: crawl a URL that returns 404. Expected: 502 fetch_failed with `run_id`; the log ends with `run_end` status error
- [x] 7.5 Local: stop MinIO and crawl. Expected: 200 with `log_uri: null`, one warning line on the host
- [x] 7.6 Live: GET /health. Expected: `object_storage: ok`
- [x] 7.7 Live: one crawl. Expected: the object exists under `logs/crawl/` in the Vultr bucket (S3 list); GET log 200; `/ui/crawl` shows the log
- [x] 7.8 Live: the `receipts/` prefix has no lifecycle rule. Expected: the only rule filters on `logs/`
