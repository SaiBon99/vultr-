# Learnings

One line each: `- YYYY-MM-DD: symptom, cause, fix.` Grouped by area, newest first. Search before debugging. Delete a gotcha once code, a check or AGENTS.md enforces it. Budget 12 KB.

## Build and tooling
- 2026-11-27: Docker 29 (containerd store) gives every cached rebuild a new image id, because BuildKit attestations carry a timestamp; build with `--provenance=false --sbom=false` when buildx is present (`setup_crawl_sandbox.sh` does).
- 2026-11-27: SvelteKit 3 build fails "module_removed_lib"; `$lib` and `$env/*` were removed. Use `#lib/...` subpath imports with `.js` extensions, `import.meta.env.PUBLIC_*` (vite `envPrefix`), relative paths to `../contracts`.
- 2026-11-27: An unanchored `lib/` in the root `.gitignore` (Python template) silently ignored `frontend/src/lib/`; anchor root-only patterns (`/lib/`). `record_check.mjs` now fails on ignored source files.
- 2026-11-27: `sv create` exits 0 but writes nothing in a non-empty dir; create in an empty temp dir and copy in.
- 2026-11-27: `minio/minio` and `quay.io/minio/minio` pulls are denied; infra uses `chainguard/minio` (no shell, so no healthcheck).
- 2026-11-27: Backend on Windows: psycopg async fails under uvicorn's ProactorEventLoop; run `uv run python scripts/serve.py`. Linux unaffected.

## Tests
- 2026-11-27: `pkill -f "<server cmd>"` inside a Bash tool call also matches (and kills) the calling shell, whose command line holds the same text; kill by PID from `pgrep -af` instead.

## Vultr and Object Storage
- 2026-11-27: vultr-cli v3.11 `object-storage create` needs both `--cluster-id` and `--tier-id`; `vultr_provision.sh` looks up `cluster list` then `cluster tiers --cluster-id`. Field names come from the CLI source, not yet from live output (ticket 17).
- 2026-11-27: Local MinIO accepts the prefix-scoped `logs/` lifecycle rule and `S3_REGION=ewr1` without a LocationConstraint error; Vultr behaviour is unverified until ticket 17.
- 2026-11-27: A /crawl run's `run_end.exit_code` is the `docker run` client's code after `docker rm -f` (-9 or 137), not the agent's own exit code; read `status` and `error_code` instead.
