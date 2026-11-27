# Add POST /crawl: one-page crawler agent in a Docker sandbox

## Why
The frontend needs a real, executed agent run on Vultr that a reviewer can call and inspect. The crawler fetches one public page, has a model summarise it, and returns the result with proof of where it ran. The hackathon brief requires agent LLM calls to go through Vultr Serverless Inference and sandboxes to run as containers on Vultr, never in the app process.

## What Changes
- New `POST /crawl` (ReviewerToken). One request starts one Docker container, runs one crawler agent and removes the container before the response. One attempt, no retry. At most 2 runs at once; a third gets 503 `sandbox_busy` (D8).
- The container runs with no network, no credentials, a read-only root filesystem, a non-root user, no capabilities and no mounts. Caps come from `SANDBOX_MAX_MEMORY_MB`, `SANDBOX_MAX_CPUS` and `SANDBOX_TIMEOUT_S`, the same as `/demo/run`.
- The host brokers both outside calls. It makes the page fetch (public-target guard before the container starts and on every redirect hop, size and type caps, logged on the host) and the model call to Vultr Serverless Inference (`CRAWLER_MODEL`, at most 512 output tokens, page text passed as untrusted data). The key never enters the container. The agent talks to the host over stdin and stdout only, one JSON message per line.
- Response `CrawlResult` carries `inference_id`, `usage`, `elapsed_ms` and a `sandbox` block with the container id, image id, `network: none` and the limits applied. The `sandbox` block is the proof of containment.
- Contracts: `openapi.yaml` 0.2.1, additive only. `/demo/run` and the existing schemas are unchanged.

## Capabilities
- New: `crawl-endpoint`.

## Out of scope
- The judge, memory writes, quarantine, the gate and receipts. The crawler writes no memory.
- Microsandbox. Docker is the sandbox runtime for this change (D7).
- Recording the broker's fetch in `audit_events` and `sessions`. That lands with the Phase 1 DB repositories; until then the fetch is only logged.
- The frontend UI that calls `/crawl`. Its mock fixture is a follow-up.
- A reusable stderr-retry path. Only `/demo/run` retries.

## Impact
- contracts/: `openapi.yaml` 0.2.1 (paths `/crawl`, schemas `CrawlRequest`, `CrawlLimits`, `CrawlSandbox`, `CrawlUsage`, `CrawlResult`, tag `crawl`).
- backend/: `app/crawl/` (guard, fetch, model, runner, service), `app/routes/crawl.py`, `sandbox/` (Dockerfile, broker-protocol agent), offline tests through POST /crawl with a fake runner and a fake resolver.
- infra/: `.env.example` gains `CRAWLER_MODEL`, `CRAWL_MAX_BYTES`, `CRAWL_SANDBOX_IMAGE`, the `SANDBOX_*` caps and `S3_REGION`. `scripts/setup_crawl_sandbox.sh` installs Docker and builds the image on the VM.
- Depends on nothing pending. The embedding change keeps contracts 0.3.0.
