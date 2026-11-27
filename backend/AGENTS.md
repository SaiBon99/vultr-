# backend/

Owner: Backend agent. Writes only inside `backend/`. Read-only inputs: [../contracts/](../contracts/README.md), [../infra/.env.example](../infra/.env.example). Root rules: [../AGENTS.md](../AGENTS.md).

## Stack
Python 3.12, uv, FastAPI, psycopg 3 (async) + pgvector, openai SDK (Vultr Serverless Inference, `https://api.vultrinference.com/v1`), boto3 (Vultr Object Storage / MinIO), cryptography (Ed25519), pytest.

## Commands
```bash
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run python scripts/serve.py --port 8000   # Windows-safe event loop for psycopg async
uv run uvicorn app.main:app --reload --port 8000  # Linux only
```

## Rules
1. Implement `contracts/openapi.yaml` exactly; response models reject extra fields. Canonical JSON, hash chain and signing follow `contracts/README.md`.
2. The gate (`app/gate.py`) is pure and deterministic: no I/O, no model calls. The judge (`app/judge.py`) runs after the freeze and can only explain or fail closed.
3. Two DB pools: `quarantine_proxy` for writes, `memory_reader` for `GET /proxy/memory/active`.
4. Every state change appends an `audit_events` row in the same transaction.
5. Tests run without network: model and S3 clients are behind interfaces with fakes. Never call live Vultr from pytest.
