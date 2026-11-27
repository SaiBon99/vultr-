# Add run logs: one transcript per subagent run in Object Storage

## Why
Each subagent run happens in a disposable sandbox that is destroyed when it finishes. Today the only trace a reviewer has is the response body and a host log line, and sandbox stderr goes to `DEVNULL`. A reviewer cannot see what the agent asked the host for, what the host answered, or why a run crashed. Object Storage holds signed receipts now; the same bucket should hold a full, redacted, hash-stamped transcript of every run, filed per session. The 0.4.0 agent-chat turns and `/demo/run` then plug into the same layer.

## What Changes
- Every `/crawl` run that took a sandbox slot writes one NDJSON transcript to Object Storage, on success and on failure, at `logs/crawl/<run_id>.jsonl`. The layout reserves `logs/sessions/<session_id>/<run_id>.jsonl` for runs that belong to a session.
- What the transcript holds:
  - a `run_start` line
  - every host<->agent protocol line, with direction and time offset
  - host-side `fetch` and `model` events (no prompts)
  - a `run_end` line with status, error code, exit code, container id, elapsed time and the captured stderr
- Secrets are redacted before upload. Page bodies over 16 KB are truncated, and the sha256 of the full text is kept. stderr is capped at 64 KB and the whole object at 1 MB. The object carries `sha256` metadata.
- The upload is best effort. It runs after the container is removed, outside the 30 s sandbox clock, and never changes the response status; on failure `log_uri` is null.
- Contracts `openapi.yaml` 0.2.2 (additive only):
  - `CrawlResult` gains `run_id` and `log_uri`
  - `Error` gains optional `run_id`, set on /crawl 502 and 504
  - new `GET /crawl/runs/{run_id}/log` (ReviewerToken) returns the transcript as `application/x-ndjson`
- `contracts/README.md` gets a wire rule for the layout, line format, caps and redaction.
- Infra:
  - an idempotent `setup_object_storage.py` (bucket, private, optional lifecycle on `logs/` only, probe)
  - a logs probe in `smoke_check.py`
  - a real cluster lookup in `vultr_provision.sh`
  - a runbook for connecting the live Vultr Object Storage to the VM
- Frontend: the `/crawl` page shows `run_id` and a run-log viewer.

## Capabilities
- New: `run-logs`.

## Out of scope
- Phase 1 work: pre-D5 gate drift, 501 routes, `001_init.sql` sync, `sessions.label`.
- Writing `logs/sessions/...` for `/demo/run` and 0.4.0 agent turns, storing `log_uri` on `agent_turns`, a `run_logged` audit event with the sha256, and `GET /sessions/{id}/logs`. All of these need the Phase 1 session lookup and audit repository.
- A separate bucket for logs. Logs share `S3_BUCKET` under `logs/` (D9).

## Impact
- contracts/: `openapi.yaml` 0.2.2 (`CrawlResult.run_id`, `CrawlResult.log_uri`, `Error.run_id`, path `/crawl/runs/{run_id}/log`); `README.md` wire rule 6; fixtures if they cover these schemas.
- backend/:
  - new `app/storage.py`, with the store classes moved out of `app/receipts.py` and re-exported from it
  - new `app/runlog.py`
  - stderr capture in `app/crawl/runner.py`
  - recording and upload in `app/crawl/service.py`
  - `run_id` in the error handler
  - the new route in `app/routes/crawl.py`
  - `tests/test_crawl_runlog.py`
- infra/: `scripts/setup_object_storage.py`, `scripts/smoke_check.py`, `scripts/vultr_provision.sh`, `.env.example`, `README.md`, `AGENTS.md`.
- frontend/: `schema.d.ts`, `client.ts`, `mock.ts`, `routes/crawl/+page.svelte`.
- .github/: `deploy.yml` scoped ruff list.
- Vultr: one Object Storage subscription in the VM's region (billable); S3 settings in the VM's env file.
- Depends on nothing pending. `embedding-fail-closed` still takes 0.3.0.
