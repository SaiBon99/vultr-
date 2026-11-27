# infra/

Owner: Infra agent. Writes only inside `infra/`. Read-only inputs: [../contracts/schema.sql](../contracts/schema.sql). Root rules: [../AGENTS.md](../AGENTS.md).

## Owns
`docker-compose.yml` (pgvector/pgvector:pg16 + MinIO), `sql/001_init.sql` (applies contracts/schema.sql, then sets role LOGIN and passwords from env), `scripts/keygen_ed25519.py`, `scripts/setup_vultr_vx1.sh`, `scripts/setup_crawl_sandbox.sh`, `scripts/vultr_provision.sh`, `scripts/smoke_check.py`, `scripts/setup_object_storage.py`, `scripts/reset_demo.py`, `.env.example`.

## Commands
```bash
docker compose -f infra/docker-compose.yml up -d
uv run --no-project --with psycopg[binary] --with boto3 python infra/scripts/smoke_check.py
uv run --no-project --with boto3 python infra/scripts/setup_object_storage.py [--logs-expire-days N]
```

## Rules
1. Scripts are idempotent: running twice changes nothing the second time.
2. `001_init.sql` must stay equivalent to `contracts/schema.sql`; never edit the contract from here.
3. `.env.example` lists every variable with a placeholder; real values live in `infra/.env` (git-ignored). Never print secrets.
4. Vultr provisioning scripts (`vultr_provision.sh`) create billable resources: dry-run by default, `--apply` to act.
