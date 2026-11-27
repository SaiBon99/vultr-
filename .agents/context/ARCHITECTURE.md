# Architecture

Authored. Keep under 80 lines; link to code instead of copying it.

## Overview
A sandboxed worker agent (Microsandbox on a Vultr VX1) reaches memory only through the host-side FastAPI Memory Proxy. The proxy gates writes deterministically, freezes risky ones in `quarantine_queue`, asks an isolated judge model to explain them, and serves a static Review UI where a person purges or overrides. Every step is hash-chained and receipted.

## Structure
- contracts/: frozen schema, OpenAPI, receipt and judge schemas, fixtures
- infra/: docker-compose (pgvector PG16, MinIO), SQL init, keygen, Vultr scripts
- backend/: FastAPI app (`app/`), pytest (`tests/`), `scripts/demo_smoke.py`
- frontend/: SvelteKit adapter-static Review UI; build output is mounted by FastAPI at /ui
- openspec/: capability specs and change proposals; .agents/context/: this record

## Data flow
1. Host `POST /proxy/sessions` (X-Host-Secret) mints a token for the sandbox.
2. Worker `POST /proxy/read` taints the session; `POST /proxy/memory/write` runs the gate: 201 to `memories` or 202 to `quarantine_queue`.
3. Judge (qwen3.8-27b on Vultr Serverless Inference) writes `judge_note` or fails closed.
4. Reviewer UI reads `/quarantine`, `/audit`, `/keys/public`, `/receipts/{id}`; `POST /quarantine/{id}/decide` signs a receipt to Object Storage.
5. Later sessions recall via `GET /proxy/memory/active` (memory_reader role, `memories` only).

## Where things go
- New endpoint: contracts change first (openspec/changes/), then backend route, then frontend client.
- New rule flag: contracts/openapi.yaml RuleFlag enum, backend gate, frontend badge.
