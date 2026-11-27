# infra runbook

## Local
```bash
cp infra/.env.example infra/.env   # optional; compose has safe local defaults
docker compose -f infra/docker-compose.yml up -d --wait
uv run --no-project --with "psycopg[binary]" --with boto3 python infra/scripts/smoke_check.py
```
Postgres 16 + pgvector on `:5432`, MinIO on `:9000` (console `:9001`, default `minioadmin`). The `minio-init` job creates bucket `quarantine-receipts`. Schema and role logins apply on first volume init; to re-apply on any DB (incl. Vultr Managed PG): `uv run --no-project --with "psycopg[binary]" python infra/scripts/apply_sql.py`.

Fresh start: `docker compose -f infra/docker-compose.yml down -v`.

## Receipt key
```bash
uv run --no-project --with cryptography python infra/scripts/keygen_ed25519.py   # --force to overwrite
```
Writes `infra/keys/receipt_ed25519.pem` (git-ignored); prints public key base64 and `key_id` only.

## Demo reset
`uv run --no-project --with "psycopg[binary]" python infra/scripts/reset_demo.py --yes`

## Vultr
- `scripts/vultr_provision.sh` : dry-run by default, `--apply` creates billable resources.
- `scripts/setup_vultr_vx1.sh` : run on the VX1 VM (KVM check, uv, node/pnpm, msb, systemd unit).
- Point `DATABASE_URL_*` and `S3_*` in `infra/.env` at the managed services, then `apply_sql.py` and `smoke_check.py`.

## Crawl sandbox (POST /crawl)
```bash
infra/scripts/setup_crawl_sandbox.sh --dry-run          # print what would change
infra/scripts/setup_crawl_sandbox.sh [--user quarantine] [--image NAME:TAG]
```
Run on the VM as a sudo-capable user; safe to repeat. It installs `docker.io` only if Docker is missing, starts the daemon if it is not running, adds the service user (default: the invoking user) to the `docker` group, and builds `backend/sandbox` as `CRAWL_SANDBOX_IMAGE` (from `--image` or the environment; default `memory-quarantine-crawler:latest`), printing the image's `sha256:` id. The `docker` group is effectively root on the VM (accepted risk, D7). Restart the API service after the first run so it picks up the group. It never reads `.env`. Rebuild after any change to `backend/sandbox/`.

`sql/001_init.sql` mirrors `contracts/schema.sql`; `sql/002_roles_login.sql` takes psql `-v proxy_password / reader_password`.
