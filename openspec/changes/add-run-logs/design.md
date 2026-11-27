# Design: add-run-logs

Written for an agent that has full repo access and the Vultr keys. Read [proposal.md](proposal.md) and [specs/run-logs/spec.md](specs/run-logs/spec.md) first. Track ownership from the root `AGENTS.md` still applies: each section below names the track that owns the files.

## Current state (2026-11-27, `main` @ aab5144)
- Object Storage is used only for receipts. `S3ObjectStore` / `InMemoryObjectStore` / `ObjectStore` live in `backend/app/receipts.py` (`put_json`, `get`, `ping`). `main.py:_build_store` builds the store from `S3_*` settings, and it is `None` when `S3_ENDPOINT_URL` is empty.
- `/crawl` runs live on the VM as `quarantine-api` (`http://45.77.138.3:8000`). `backend/app/crawl/runner.py` starts the container with `stderr=asyncio.subprocess.DEVNULL`. `backend/app/crawl/service.py:_Broker` handles the protocol (`task`, `fetch`, `fetch_result`, `model`, `model_result`, `result`).
- Local MinIO and its bucket init are in `infra/docker-compose.yml` (chainguard images, D6). `smoke_check.py` only checks `head_bucket`, with `region_name="us-east-1"` hard-coded.
- `vultr_provision.sh` has `OBJ_CLUSTER=REPLACE_WITH_CLUSTER_ID`.
- CI (`.github/workflows/deploy.yml`) runs `pytest -k crawl` and `ruff check` on a fixed file list, then deploys `main` to the VM through `infra/scripts/publish.sh`.

## Object layout and line format
Keys:
- `logs/crawl/<run_id>.jsonl`: a run without a session (every `/crawl` run today).
- `logs/sessions/<session_id>/<run_id>.jsonl`: reserved for session runs (`/demo/run`, 0.4.0 agent turns). `run_log_key()` supports it now; nothing writes it in this change.

Put parameters: `ContentType=application/x-ndjson`, `Metadata={"sha256": <hex of body>, "kind": "crawl", "session-id": ""}`.

Lines (`seq` counts up across `msg` and `host` lines; `t_ms` is milliseconds since `run_start`):
```json
{"type":"run_start","run_id":"…","kind":"crawl","session_id":null,"started_at":"2026-11-27T12:00:00Z","limits":{"memory_mb":512,"cpus":1,"timeout_s":30},"image_id":"sha256:…"}
{"type":"msg","seq":1,"t_ms":3,"dir":"host_to_agent","msg":{"type":"task","url":"https://example.com"}}
{"type":"msg","seq":2,"t_ms":410,"dir":"agent_to_host","msg":{"type":"fetch","url":"https://example.com"}}
{"type":"host","seq":3,"t_ms":690,"event":"fetch","final_url":"https://example.com/","status":200,"bytes":1256,"content_type":"text/html"}
{"type":"msg","seq":4,"t_ms":691,"dir":"host_to_agent","msg":{"type":"fetch_result","final_url":"…","content_type":"text/html","body":"…","body_truncated":false}}
{"type":"msg","seq":5,"t_ms":720,"dir":"agent_to_host","msg":{"type":"model","page_title":"…","page_text":"…"}}
{"type":"host","seq":6,"t_ms":1980,"event":"model","model":"qwen3.8-27b","inference_id":"…","usage":{…},"latency_ms":1255}
{"type":"msg","seq":7,"t_ms":1981,"dir":"host_to_agent","msg":{"type":"model_result","title":"…","summary":"…","key_points":["…"]}}
{"type":"msg","seq":8,"t_ms":1990,"dir":"agent_to_host","msg":{"type":"result","title":"…","summary":"…","key_points":["…"]}}
{"type":"run_end","status":"ok","http_status":200,"error_code":null,"exit_code":0,"container_id":"…","elapsed_ms":2100,"stderr":"","stderr_truncated":false,"lines_dropped":0}
```
Rules:
- **Malformed agent line:** `{"type":"msg",…,"dir":"agent_to_host","raw":"<utf-8, errors=replace, ≤4 KB>"}`.
- **Truncation:** a `fetch_result.body` over 16 KB becomes its first 16 KB, plus `body_truncated:true`, `body_chars:<len of full>` and `body_sha256:<hex of utf-8 full>`. The agent's `model.page_text` follows the same rule, as `page_text_truncated`, `page_text_chars` and `page_text_sha256`.
- **Object cap:** 1 MB. Serialize `run_start` and `run_end` first so they are always kept. Add `msg`/`host` lines in order until the next one would pass the cap, then count the rest in `lines_dropped`.
- **Redaction:** in `to_bytes()`, replace every secret of 8 or more characters (`VULTR_INFERENCE_API_KEY`, `HOST_SECRET`, `REVIEWER_TOKEN`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`) in the serialized text with `[REDACTED]`. Do this before computing `sha256`. JSON-escaped forms of the secrets are equal to the raw value for the token alphabets in use; still, apply the replacement to both `json.dumps(secret)[1:-1]` and the raw value.
- **No prompts:** the system prompt and the full model request are never logged. The `model` host event carries only model, inference_id, usage and latency.

## Backend (`backend/`, Backend agent)
1. **`app/storage.py` (new):**
   - Move `ObjectStore` (Protocol), `InMemoryObjectStore` and `S3ObjectStore` here from `app/receipts.py`, and re-export them from `receipts.py` (`from app.storage import …  # noqa: F401`) so `main.py` and the tests keep working.
   - Add `put_bytes(key, body, *, content_type, metadata=None) -> str` to all three; `put_json` calls `put_bytes(..., content_type="application/json")`. Add `head(key) -> dict | None`, which returns the metadata, for tests and verification.
   - Build the S3 client with `botocore.config.Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2, "mode": "standard"}, signature_version="s3v4", s3={"addressing_style": "path"})`. Path style works on both MinIO and Vultr (`https://<cluster>.vultrobjects.com/<bucket>/<key>`).
   - `InMemoryObjectStore` keeps `metadata[key]` and `content_types[key]`, and gets a `fail: bool` flag that makes puts raise, for the best-effort test.
2. **`app/runlog.py` (new):**
   - `RunLog(run_id, kind, session_id, limits, clock=time.monotonic)` with:
     - `start(image_id)`
     - `sent(msg: dict)`
     - `received(line: bytes, parsed: dict | None)`
     - `host(event: str, **fields)`
     - `finish(*, status, http_status, error_code, exit_code, container_id, elapsed_ms, stderr, stderr_truncated)`
     - `to_bytes(secrets: list[str]) -> bytes`
   - The truncation rules apply inside `sent()` and `received()`.
   - `run_log_key(kind, run_id, session_id=None)`.
   - `async upload_run_log(store, log, secrets) -> str | None`: if `store is None`, return None. Otherwise compute the bytes and sha256, then `await run_in_threadpool(store.put_bytes, key, body, content_type="application/x-ndjson", metadata={...})`. On any `Exception`, run `log.warning("run log upload failed run_id=%s err=%s", run_id, type(exc).__name__)` and return None.
   - `Settings.log_secrets` property: the non-empty `get_secret_value()` of the five secrets.
3. **`app/crawl/runner.py`:**
   - `stderr=asyncio.subprocess.PIPE` in `DockerRunner.start`.
   - `ProcessRun.__init__` starts `self._stderr_task = asyncio.create_task(self._drain_stderr())`. That task reads chunks into a `bytearray`, keeps the first 64 KB, sets `stderr_truncated`, and discards the rest so the pipe never fills.
   - `async stderr_text() -> tuple[str, bool]` waits for the task, with a 1 s timeout after the process exits. `cleanup()` cancels the task if it is still running. It stays idempotent.
   - The Docker argv is unchanged; `test_crawl_sandbox.py`'s argv assertions must still pass.
   - Update the test runner in `tests/crawl_fakes.py` the same way if it builds `ProcessRun` with `stderr=DEVNULL`.
4. **`app/crawl/service.py`:**
   - In `crawl()`, after `slots.take()`: `run_id = str(uuid4())` and `runlog = RunLog(run_id, "crawl", None, runner.limits)`.
   - Pass `runlog` to `_Broker`. Then:
     - `_send` calls `runlog.sent(message)` before writing.
     - `_next` calls `runlog.received(line, parsed_or_None)`. Record it before raising on a malformed line.
     - `_fetch` adds a `host("fetch", …)` event from `Page` (`final_url`, status if available, byte length, content_type).
     - `_model` adds a `host("model", …)` event from `Summary` (model, inference_id, usage, latency).
   - `runlog.start(image_id)` runs once `runner.start()` returns; read `image_id` from the run (`DockerRun.image_id`; the fake runner may give `None`).
   - Keep the outcome in local variables (`status`, `http_status`, `error_code`, `exc`). In the existing `finally`:
     1. run `run.cleanup()` and `slots.give()` as today
     2. `stderr, truncated = await run.stderr_text()` when `run` exists
     3. `runlog.finish(...)`
     4. `log_uri = await upload_run_log(store, runlog, settings.log_secrets)`
   - On error, set `exc.run_id = run_id` and re-raise.
   - `crawl()` gains a `store` parameter; `routes/crawl.py` passes `request.app.state.store`.
   - `CrawlResult` gains `run_id` and `log_uri`.
5. **Errors:**
   - `CrawlError` (`app/crawl/errors.py`) and `ApiError` (`app/deps.py`) get `run_id: str | None = None`.
   - The `http_error` handler in `main.py` adds `body["run_id"]` when it is set.
   - Check how the crawl route maps `CrawlError` today, and attach `run_id` on that same path.
6. **`app/models.py`:** `CrawlResult.run_id: UUID`, `CrawlResult.log_uri: str | None`, `Error.run_id: UUID | None = None` (optional, omitted when None).
7. **`app/routes/crawl.py`:**
   - `@router.get("/crawl/runs/{run_id}/log", operation_id="getCrawlRunLog", dependencies=[ReviewerAuth], responses={…})`.
   - If `store is None`, raise `ApiError(503, "Object storage is not configured", "storage_missing")`.
   - Otherwise `body = await run_in_threadpool(store.get, run_log_key("crawl", str(run_id)))`. If `None`, raise `ApiError(404, "Run log not found", "not_found")`; else return `Response(body, media_type="application/x-ndjson")`.
8. **`tests/test_crawl_runlog.py`** (`crawl` in the name puts it in CI's `-k crawl` run). Reuse the fixtures from `tests/test_crawl.py` and `tests/crawl_fakes.py`, and give the app an `InMemoryObjectStore`. Cases:
   - success: `run_id` and `log_uri` are in the response; the object's first line is `run_start`, the last is `run_end` `ok`; the `msg` directions and types come in protocol order; there are `host` fetch and model events; the `sha256` metadata matches the bytes
   - 502 agent_crash and 504 timeout: the body has `run_id`, the transcript exists, and `run_end.error_code` matches
   - a malformed agent line is logged as `raw`
   - 422 unsafe_target and 503 sandbox_busy: no `run_id` and no object
   - redaction: a page body and agent stderr containing `REVIEWER_TOKEN` and the inference key; neither appears in the object
   - a 200 KB page: the logged body is 16 KB with the correct `body_sha256`
   - stderr capture and the 64 KB cap
   - a store with `fail=True`: 200 with `log_uri: null`
   - GET log: 200 with identical bytes and `application/x-ndjson`; 404; 401 without the token; 503 without a store
   - `from app.receipts import S3ObjectStore, InMemoryObjectStore` still works
   - `test_openapi_declares_every_contract_path` covers the new path

## Contracts (`contracts/`, Coordinator)
- `openapi.yaml`:
  - `info.version: 0.2.2`, with a changelog line in the description like the 0.2.1 one.
  - `CrawlResult`: add `run_id` and `log_uri` to the properties and `required`.
  - `Error`: optional `run_id: {type: string, format: uuid}`.
  - New path `/crawl/runs/{run_id}/log` (tag `crawl`, `ReviewerToken`) with responses 200 (`application/x-ndjson`, `type: string`), 401, 404 and 503 (`Error`).
  - The `/crawl` description says a transcript is written for every started run.
- `README.md`: wire rule 5, covering the run-log layout, line types, caps, redaction order (redact, then hash) and the `sha256` metadata. Link it from this design.
- Fixtures: if `contracts/fixtures/` or `check_contracts.py` validate `CrawlResult`, update or add a fixture with `run_id` and `log_uri`. Run the contracts command from the root `AGENTS.md`.

## Infra (`infra/`, Infra agent)
- **`scripts/setup_object_storage.py` (new):**
  - Load the env with `_env.load_env()` and build a boto3 client from `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `S3_REGION`, path style and s3v4.
  - Steps:
    1. `head_bucket`; on 404, `create_bucket` (with `CreateBucketConfiguration` only when the endpoint requires it). On 403, the name belongs to someone else: exit 1 and say to pick a unique `S3_BUCKET`.
    2. Check that the bucket ACL has no public grants, and warn if it does.
    3. With `--logs-expire-days N`, `put_bucket_lifecycle_configuration` with one rule `{ID: "expire-run-logs", Filter: {Prefix: "logs/"}, Status: Enabled, Expiration: {Days: N}}`. First read any existing rules and keep those that aren't ours. If the endpoint rejects it, warn and continue.
    4. Put, get and delete a probe at `logs/_probe/<uuid>.jsonl` with `sha256` metadata, and check the round trip.
  - Print PASS/FAIL lines like `smoke_check.py`; never print keys. Idempotent.
- **`scripts/smoke_check.py`:** use `S3_REGION` from the env, and add a "s3 logs/ put-get-delete" check.
- **`scripts/vultr_provision.sh`:**
  - Replace the placeholder with a lookup step that lists Object Storage clusters (and tiers, if the CLI version requires a tier), picks the one whose region matches `REGION`, and fails if there is none.
  - Check the exact subcommands and flags with `vultr-cli object-storage --help` before writing them.
  - After create, print the next step: get the S3 hostname and keys from the subscription, then set them in the VM env file.
  - Keep dry-run as the default.
- **`.env.example`:**
  - Note that run logs share `S3_BUCKET` under `logs/`.
  - Note that Vultr bucket names must be unique on the cluster, and that `S3_REGION` is the cluster id (for example `ewr1`).
  - Optional `S3_LOGS_EXPIRE_DAYS=` (used only by `setup_object_storage.py`).
- `README.md` and `AGENTS.md`: list the new script and its command.

## Frontend (`frontend/`, Frontend agent)
- Regenerate `src/lib/api/schema.d.ts` from `contracts/openapi.yaml` 0.2.2 with the existing generator script (see `frontend/AGENTS.md`).
- `src/lib/api/client.ts`: `getCrawlRunLog(runId): Promise<RunLogLine[]>` splits on newlines and parses each line. Mirror it in `mock.ts` with a short sample transcript (success and error).
- `routes/crawl/+page.svelte`: show `run_id`. Add an expandable "Run log" list with one row per line (type, dir, seq, t_ms, short summary; long bodies collapsed) for both success and error responses (`run_id` from the error body). Follow `frontend/DESIGN.md` and the Acme tokens.
- `pnpm run check:unified` and the e2e smoke test pass.

## CI and record (Coordinator)
- `.github/workflows/deploy.yml`: add `app/storage.py app/runlog.py app/receipts.py app/crawl/errors.py app/routes/crawl.py tests/test_crawl_runlog.py` to the scoped `ruff check` list. Keep the list deduplicated.
- `DECISIONS.md`: D9 "Run logs share the receipts bucket under logs/". Why: one subscription, one credential pair, and the lifecycle rule is limited to the `logs/` prefix. Revisit if logs need a different retention or access policy from receipts.
- `STATE.md`: Working and Not-working items with `closed when:`. `LEARNINGS.md`: anything that differed from expectations on Vultr (bucket naming, lifecycle support, addressing style).

## Live hookup runbook (admin machine with keys)
Rules: never print, echo or commit keys or `.env` contents. Write secrets only into the VM env file, mode 600. Creating an Object Storage subscription is **billable**: confirm with the user before `--apply` or a console create.
1. **Region:** `vultr-cli instance list` and find the instance with IP `45.77.138.3`; note its region. The Object Storage cluster must be in the same region, or the nearest one that offers Object Storage. Record the choice in STATE.md.
2. **Create:** in the Vultr console (Object Storage → Add, same region, label `quarantine-objects`), or with `bash infra/scripts/vultr_provision.sh --region <region>` (dry run), and after confirmation `--apply`. Then read the S3 hostname, access key and secret key from the subscription.
3. **Find the live env file:** on the VM, `systemctl cat quarantine-api | grep EnvironmentFile`. `publish.sh` refers to `/opt/vultr-app/.env`; `setup_vultr_vx1.sh` writes `/opt/quarantine/infra/.env`. Use whichever the unit loads.
4. **Set** these, without echoing values (use an editor or `install -m 600` from a local temp file, then shred it):
   - `S3_ENDPOINT_URL=https://<cluster>.vultrobjects.com`
   - `S3_ACCESS_KEY`
   - `S3_SECRET_KEY`
   - `S3_BUCKET=quarantine-receipts`, or a unique name if that one is taken
   - `S3_REGION=<cluster id>`

   Check the file is mode 600 and owned by the service user.
5. **Bucket:** run `uv run --no-project --with boto3 python infra/scripts/setup_object_storage.py --logs-expire-days 30`, either on the VM with that env file loaded or on the admin machine with the same values in `infra/.env`. Run it twice; the second run must report no changes.
6. **Deploy:** merge the change to `main` (CI checks, then publishes), or `bash infra/scripts/publish.sh --host 45.77.138.3 --user deploy --identity <key>`. Then `sudo systemctl restart quarantine-api` if the env file changed after the last publish.
7. **Prove it:** run the live checks in tasks.md §7 and record the results in STATE.md.
