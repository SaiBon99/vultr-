## ADDED Requirements

### Requirement: One transcript per started run
Every subagent run that took a sandbox slot SHALL produce exactly one NDJSON transcript in Object Storage, whether it succeeded or failed. Requests refused before a slot is taken (422 unsafe_target, 503 sandbox_busy, 503 inference_not_configured) SHALL NOT produce a transcript. The upload SHALL happen after the container is removed and outside the SANDBOX_TIMEOUT_S clock.

#### Scenario: Successful crawl
- **WHEN** a reviewer posts a public URL and the run completes
- **THEN** the response carries a `run_id` (uuid) and a `log_uri` of `s3://<S3_BUCKET>/logs/crawl/<run_id>.jsonl`, and that object exists

#### Scenario: Failed crawl
- **WHEN** a run ends in 502 (any code) or 504 timeout
- **THEN** the error body carries `run_id`, and the transcript for that run exists with a `run_end` line whose `status` is `error` and whose `error_code` and `http_status` match the response

#### Scenario: Refused before start
- **WHEN** a request is refused with 422 unsafe_target or 503 sandbox_busy
- **THEN** no transcript is written and the error body has no `run_id`

### Requirement: Object layout
Transcripts SHALL be stored in `S3_BUCKET` under the `logs/` prefix only: `logs/crawl/<run_id>.jsonl` for runs without a session, and `logs/sessions/<session_id>/<run_id>.jsonl` for runs in a session. They SHALL be stored with ContentType `application/x-ndjson` and metadata `sha256` (lowercase hex of the stored bytes), `kind` and `session-id` (empty when there is no session). Nothing SHALL be written under `receipts/` by this capability.

#### Scenario: Integrity metadata
- **WHEN** a transcript is downloaded
- **THEN** sha256 of its bytes equals its `sha256` metadata

### Requirement: Transcript framing
Each line SHALL be one JSON object. The first line SHALL be `run_start` (run_id, kind, session_id, started_at, limits, image_id). The last line SHALL be `run_end` (status, http_status, error_code, exit_code, container_id, elapsed_ms, stderr, stderr_truncated, lines_dropped).

#### Scenario: Framing lines present
- **WHEN** any transcript is read
- **THEN** its first line has type `run_start` and its last line has type `run_end`

### Requirement: Protocol and host events
Every protocol line SHALL be logged in order as `msg` (seq, t_ms, dir `host_to_agent` or `agent_to_host`, msg). Host-side calls SHALL be logged as `host` events `fetch` and `model`, without prompts. An agent line that is not valid JSON SHALL be logged as `raw` text, capped at 4 KB.

#### Scenario: Protocol order
- **WHEN** a crawl run completes
- **THEN** the `msg` lines appear as task, fetch, fetch_result, model, model_result, result, with one `host` fetch and one `host` model event

#### Scenario: Malformed agent output
- **WHEN** the agent writes a line that is not JSON and the run ends with 502 agent_crash
- **THEN** the transcript has a `msg` line with `raw` holding that text, followed by `run_end`

### Requirement: Redaction
Before upload, every configured secret value of 8 or more characters (VULTR_INFERENCE_API_KEY, HOST_SECRET, REVIEWER_TOKEN, S3_ACCESS_KEY, S3_SECRET_KEY) SHALL be replaced with `[REDACTED]` wherever it appears in the transcript.

#### Scenario: Secret echoed by a page or the agent
- **WHEN** a fetched page, an agent line or stderr contains the reviewer token or the inference key
- **THEN** the stored object does not contain either value

### Requirement: Size caps
A `fetch_result.body` longer than 16 KB SHALL be truncated to 16 KB and annotated with `body_truncated: true`, `body_chars` and `body_sha256` of the full text. stderr SHALL be capped at 64 KB, with `stderr_truncated` set. A transcript SHALL NOT exceed 1 MB. Once the cap is reached, further `msg` lines SHALL be dropped and counted in `run_end.lines_dropped`; `run_start` and `run_end` SHALL always be present.

#### Scenario: Large page
- **WHEN** the fetched page text is 200 KB
- **THEN** the logged body is 16 KB and `body_sha256` equals sha256 of the full text

### Requirement: Sandbox stderr capture
The host SHALL capture sandbox stderr concurrently, so a noisy sandbox can never block on a full pipe. It SHALL keep at most 64 KB. The capture SHALL NOT add any environment variable, mount or network to the container.

#### Scenario: Agent writes to stderr
- **WHEN** the agent writes a traceback to stderr and exits
- **THEN** `run_end.stderr` holds the traceback

### Requirement: Best-effort upload
A missing store or a failed upload SHALL NOT change the response status or body, apart from `log_uri` being null. The failure SHALL be logged once on the host, without the transcript body.

#### Scenario: Object Storage down
- **WHEN** the store raises on upload after a successful run
- **THEN** the API returns 200 with `log_uri: null`

### Requirement: Reviewer read access
`GET /crawl/runs/{run_id}/log` SHALL require X-Reviewer-Token. It SHALL return the stored transcript bytes as `application/x-ndjson`, 404 not_found when there is no such object, and 503 storage_missing when Object Storage is not configured. The sandbox SHALL have no path to this endpoint or to the bucket.

#### Scenario: Read a run log
- **WHEN** a reviewer requests the log of a run that exists
- **THEN** the API returns 200 with bytes identical to the stored object

#### Scenario: No token
- **WHEN** the request has no X-Reviewer-Token
- **THEN** the API returns 401

### Requirement: Lifecycle scope
An expiry rule for transcripts, if configured, SHALL apply to the `logs/` prefix only. Receipts SHALL never expire through it.

#### Scenario: Expiry configured
- **WHEN** `setup_object_storage.py --logs-expire-days 30` is run
- **THEN** the bucket has one lifecycle rule filtered on prefix `logs/`, and objects under `receipts/` are unaffected
