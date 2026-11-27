# Agent Sandbox Runner and Memory Quarantine

Two systems in one repo, built for the Vultr Agent Runtime Hackathon (Stockholm MLOps, Meetup #42). Both run every model call on Vultr Serverless Inference and run untrusted code inside Microsandbox microVMs on a Vultr VX1 VM.

1. **Agent Sandbox Runner (Pattern A).** A goal goes in. The model writes Python, the code runs in a microVM, and stderr feeds back for a retry. Code: `backend/app/{planner,sandbox,runner}.py`.
2. **Memory Quarantine (spec.md).** A buyer assistant's persistent memory is gated by deterministic code. Poisoned writes are frozen, a judge model explains them, and a reviewer purges or overrides them. Code: `backend/app/memory/`.

Background and the event requirements: [docs/hackathon-instructions.md](docs/hackathon-instructions.md). Memory-quarantine design, results, and limits: [docs/memory-quarantine.md](docs/memory-quarantine.md).

## Architecture

```
 browser ──► FastAPI on VX1 VM (Amsterdam)
                │
                ├─ Pattern A: POST /tasks
                │     planner ──► Serverless Inference (worker model)
                │     SandboxRunner ──► Microsandbox microVM (default network)
                │
                └─ Memory quarantine: POST /demo/runs, /proxy/*, /ui
                      model calls ──► Serverless Inference (worker + judge models)
                      gate.py      deterministic verdict per memory write
                      store.py ──► Managed PostgreSQL (memories, quarantine_queue, audit_events)
                      SandboxRunner ──► Microsandbox microVM, egress allowed to the proxy only
                                        (calls /proxy/read, /proxy/memory/*; prints fake tool calls)
```

The app process never executes model-written code. Only sandboxes do. Sandboxes never hold the inference key or the database URL.

## Containment

| Property | How it is enforced |
|---|---|
| Process isolation | Each run is its own microVM, with its own kernel. Test: `tests/test_containment.py`. |
| Secret hygiene | Sandboxes are created without `env`. The memory worker's script contains only the proxy URL and a session_id. Tests check both. |
| Network | Memory-demo sandboxes allow egress to the proxy's IP and port only. Test: `tests/test_egress_integration.py`. |
| Resource limits | CPU, memory, `max_duration`, and an exec timeout on every run. |
| Lifecycle | `ephemeral=True`, and `destroy()` in `finally`. |
| Sibling isolation | Sandboxes cannot reach each other. Test: `test_sibling_sandboxes_cannot_reach_each_other`. |
| Memory writes | Gated by provenance. Sandboxes cannot choose a naive gate or a namespace. |

## Repository layout

```
backend/app/config.py            settings from env / .env
backend/app/sandbox.py           Microsandbox wrapper with containment limits and optional egress allow-list
backend/app/planner.py           Pattern A: model writes the script
backend/app/runner.py            Pattern A: plan -> execute -> retry loop
backend/app/main.py              FastAPI routes and static frontend; mounts the memory router
backend/app/memory/gate.py       deterministic verdicts (CLEAN_USER, TAINTED_UNREVIEWED, POLICY_BLOCKED, INCONCLUSIVE)
backend/app/memory/service.py    sessions, taint, writes, recall, review actions (store and judge injected)
backend/app/memory/store.py      Managed PostgreSQL: memories, quarantine_queue, audit_events (hash chain)
backend/app/memory/judge.py      isolated judge model; strict JSON; failure fails closed
backend/app/memory/proxy.py      HTTP routes: /proxy/*, /ui, /audit, /demo/runs
backend/app/memory/honeypot.py   seeded poison, canary, and the outbound-call monitor
backend/app/memory/worker.py     sandbox script builder and tolerant model-reply parsing
backend/app/memory/demo.py       naive vs gated demo runner
frontend/index.html              Pattern A goal form
docs/                            hackathon instructions, memory-quarantine design and results
scripts/setup_vm.sh              idempotent host setup (KVM check, msb install, venv)
tests/                           unit tests (no KVM), and integration tests marked `integration` (KVM + msb)
```

## Setup

Requirements: Linux with KVM (`/dev/kvm`), Python 3.12+, a Vultr Serverless Inference key, and a Managed PostgreSQL database for the memory part.

```bash
bash scripts/setup_vm.sh           # KVM check, msb install, msb doctor, .venv
cp .env.example .env               # fill in the keys, models, DATABASE_URL, REVIEW_TOKEN, PROXY_BASE_URL
```

Notes:

- `setup_vm.sh` needs `python3.12-venv` installed (on Ubuntu: `apt install python3.12-venv`).
- If `setup_vm.sh` adds you to the `kvm` group, log out and back in first.
- Microsandbox refuses storage roots that other accounts can reach. On the VX1 VM we set `chmod 700` on the service user's home and `~/.microsandbox`.
- `PROXY_BASE_URL` must be an IP address for the demo's egress policy (`http://<ip>:8000`).

## Run

```bash
.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- Pattern A: `http://<host>:8000/`. Try: *Write and run a Python script that prints the first 10 Fibonacci numbers, and test it in an isolated sandbox.*
- Memory quarantine review: `http://<host>:8000/ui?token=<REVIEW_TOKEN>`
- Start the demo: `curl -X POST -H "X-Review-Token: <token>" http://<host>:8000/demo/runs`, then `GET /demo/runs` with the same header.

On the deployed VM the service runs under systemd as `vultr-app` (unit file `/etc/systemd/system/vultr-app.service`). The app lives in `/opt/vultr-app`, and `.env` is mode 600.

## Test

```bash
.venv/bin/pytest                                  # unit tests, no KVM or database needed
TEST_HOST_IP=<host ip> .venv/bin/pytest -m integration   # real sandboxes: containment and egress (needs KVM and msb)
```

The unit suite covers the gate rule table, judge parsing, the service with an in-memory store, proxy routes, the reviewer-token guard, and the sandbox script (including a check that no DSN or key appears in it).

## Deployed

| What | Where | Status |
|---|---|---|
| VX1 VM (2 vCPU, 8 GB, 120 GB NVMe) | Vultr, AMS, `45.77.138.3` | Running Ubuntu 24.04, KVM available |
| Managed PostgreSQL 16 + pgvector available | Vultr, AMS, `vultr-dbaas-hobbyist-cc-1-25-1` | Running |
| Serverless Inference | `Hackathon` subscription | Worker `qwen3.8-27b`, judge `glm-5.3` |
| Integration tests on the VM | containment (6) and egress (1) | Pass |

## Status

- [x] Pattern A: sandbox wrapper, planner, retry loop, API, frontend
- [x] Containment tests run on a KVM host (the VM)
- [x] Memory quarantine: gate, storage (option B), judge, review UI, audit chain, honeypot demo
- [x] Demo runs on the VM with live Serverless Inference (results in docs/memory-quarantine.md)
- [ ] Ed25519 receipts in Object Storage
- [ ] eval.py (10 attacks + 6 benign)
- [ ] HTTPS on the public URL
- [ ] Per-user review auth (today: one shared `REVIEW_TOKEN`)
- [ ] Demo video, including a containment moment
