# Vultr Agent Runtime Hackathon: Instructions

Source: [#42 - Vultr Agent Runtime Hackathon](https://luma.com/stockholm-nn3n?tk=7BTEYO) (Stockholm MLOps, Meetup #42), crawled with Playwright on 2026-11-27. Linked Vultr docs were crawled the same day. Quotes and requirements below are from the event page. Anything marked **Repo status** is an assessment of this repository, not event text.

## Event details

| | |
|---|---|
| Date | Friday, 27 November 2026, 09:00 to 21:00 |
| Venue | Netlight Consulting AB, Regeringsgatan 25, 111 53 Stockholm, Sweden |
| Presented by | Stockholm MLOps |
| Host | Patrick Couch |
| Registration | Subject to host approval ("Request to Join") |
| Format | Full-day, 12-hour hackathon. Teams of 2 to 4. Solo attendees are matched into teams. |

### Agenda

| Time | Item |
|---|---|
| 09:00 | Doors open. Breakfast and registration. |
| 09:30 | Welcoming remarks |
| 10:00 | Hacking begins |
| 12:00 | Lunch |
| 19:00 | **Project submission deadline** |
| 19:00 | Raffle |
| 19:15 | Pizza, drinks, networking |
| 21:00 | Doors close |

A Vultr team is on site to help. A more detailed agenda was promised.

## The challenge

> Build a web-based agent that performs real work (writing and running code, or operating a real browser), with every action contained inside a sandbox running on Vultr. Your system should act as a centralized control layer that plans a task, dispatches it to an isolated execution environment, and returns verifiable output.

Expectations:

- Multi-step agentic workflows.
- Real executed results, not described ones.
- A production-style web application, running on Vultr infrastructure.
- **Containment first.** "An agent that only chats is a demo; an agent that executes safely is a product."

### Execution patterns (build one or both)

**Pattern A: Sandboxed code execution.** The user asks, the model writes code, the code runs in a container, real output returns, and the model explains it. On error, stderr is fed back for a retry.

Example ideas: CSV Analyst, Prove-It Code Reviewer, Chart Anything, File Fixer, Self-Healing Runner.

**Pattern B: Sandboxed browser use.** The user gives a goal, the model plans, Playwright in a container navigates, clicks, and types, screenshots return, and a vision model on Serverless Inference verifies the result. This repeats, with a human approving anything final.

Example ideas: Comparison Shopper, Form Filler, Site QA Sweep, Research with Receipts, Page Watcher.

### Containment focus

Address real safety and reliability problems in agent execution:

1. **Process isolation.** Execution never touches the host or the app runtime.
2. **Secret hygiene.** No API keys or credentials inside the sandbox.
3. **Resource limits.** Time and memory caps on every run.
4. **Lifecycle discipline.** Reset or destroy the environment after each task.

"Show how isolation makes autonomous execution shippable."

## Requirements

### Mandatory

- Deploy a **VM-based backend on Vultr**.
- **Agent LLM calls must go through Vultr Serverless Inference.** Base URL: `https://api.vultrinference.com/v1` (OpenAI-compatible).
- Vultr is the **central system of control and orchestration**, not just static hosting.
- Sandboxes run as containers or throwaway instances on Vultr, **never inside the app process**.
- The web app must be **reachable from a public browser** and offer a real product-style flow, not only a local demo.
- A sandbox isolated from the application process.

### Strongly recommended

- Docker container as the sandbox boundary.
- REST or WebSocket APIs for run status and streaming output.
- Web dashboards showing the execution loop, retries, and screenshot trails.
- Approve-before-submit gates on any irreversible browser action.

### Optional

- Vultr API to create a throwaway instance per task and destroy it afterwards, making Vultr the sandbox fabric.
- Vision-capable models on Serverless Inference for screenshot reasoning.
- Playwright in Docker for browser automation.

## Deliverables (each team)

1. GitHub repository with setup and documentation.
2. Vultr VM backend deployment, with agent LLM calls through Vultr Serverless Inference.
3. Public demo URL.
4. Recorded demo video.
5. **One containment moment in the video.** The sandbox absorbs something unsafe, such as `rm -rf`, an infinite loop, or a hostile web page.
6. Clear explanation of architecture and use case.

## Prizes

The three most impressive projects formally submitted receive cash prizes and additional Vultr credits. More details were promised later.

## Credits

- $200 in free Vultr credits per participant.
- Activate them through the "Vultr Setup Guide". The Luma page does not link that guide directly. It links a redemption walkthrough video: `https://del1.vultrobjects.com/tech-talk/redeem-vultr-credits-for-hackathons.mp4`.

## Prerequisites

- Laptop and GitHub account.
- Working Python (or TypeScript) and API experience.
- Basic LLM familiarity.
- No special hardware.

## Resources

| Resource | Link |
|---|---|
| Serverless Inference provisioning | https://docs.vultr.com/products/serverless/inference/provisioning |
| Live model list | https://api.vultrinference.com/v1/models |
| Vultr API (throwaway-instance pattern) | https://www.vultr.com/api/ |
| Agent sandboxing guide on Vultr | https://docs.vultr.com/how-to-set-up-agent-sandboxing-on-vultr-cloud-compute |

Open-source sandbox examples listed on the event page: [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox), [gVisor](https://gvisor.dev/), [E2B](https://github.com/e2b-dev/e2b), [Microsandbox](https://microsandbox.dev/).

## Vultr Serverless Inference: setup notes

From the provisioning guide (crawled 2026-11-27):

1. In the Vultr Console, go to **Compute > Serverless Inference**.
2. Click **Create Inference**, enter a label, acknowledge the usage-based cost, and click **Create Inference**.
3. Confirm the subscription shows **Active**.
4. Get the subscription's API key (the crawled guide does not cover this step) and put it in `.env` as `VULTR_INFERENCE_API_KEY`. Never commit it.
5. Pick a model ID from the live list and put it in `.env` as `VULTR_INFERENCE_MODEL`.

Chat-capable models listed on 2026-11-27 (text output). The list changes, so re-check it before the event:

| Model ID | Input modalities | Notes |
|---|---|---|
| `deepseek-v4.1-flash-1017` | text, image, file | DeepSeek V4.1 Flash |
| `deepseek-v4.1-flash-1017:free` | text, image, file | Free tier variant |
| `glm-5.3` | text, image, file | GLM 5.3 |
| `glm-5.3-flash` | text, image, file, video | GLM 5.3 Flash |
| `mimo-v2.6-flash` | text, image, file, audio, video | MiMo V2.6 Flash |
| `mimo-v2.6-pro` | text, image, file, audio, video | MiMo V2.6 Pro |
| `minimax-m3.1-flash` | text, image, file, video | MiniMax M3.1 Flash |
| `nemotron-3-nano-omni-30b-a3b-reasoning` | text, image, file, audio, video | Nemotron 3 Nano Omni |
| `qwen3.8-27b` | text, image, file, video | Qwen 3.8 27B |
| `qwen3.8-flash-next` | text, image, file, video | Qwen 3.8 Flash Next |
| `qwen3.8-flash-next:free` | text, image, file, video | Free tier variant |

Models with vision input (for example `glm-5.3`, `qwen3.8-27b`, `mimo-v2.6-pro`) are the candidates for Pattern B screenshot verification. The list also includes a content-safety model, `nemotron-3.5-content-safety`, which is not a chat model.

## Agent sandboxing: setup notes

From the Vultr guide "Agent Sandboxing on Vultr Cloud Compute with Microsandbox" (crawled 2026-11-27):

- Requires a VX1 instance running Ubuntu 24.04, as a non-root user with sudo.
- Microsandbox runs each sandbox as its own microVM (libkrun over KVM), with a separate kernel from the host.
- Setup:
  1. `sudo usermod -aG kvm $USER`, then `newgrp kvm` or log out and back in.
  2. Check `ls -l /dev/kvm`.
  3. Install: `curl -fsSL https://install.microsandbox.dev | sh`, then log out and back in for PATH.
  4. Verify with `msb --version` and `msb doctor`. The reflink warning is informational on ext4.
- Isolation facts from the guide:
  - Sandboxes have outbound internet by default.
  - Sandboxes cannot reach each other.
- The Python SDK is `pip install microsandbox`. Key calls are `Sandbox.create(name, image=..., cpus=..., memory=..., replace=True)`, `sandbox.exec(...)`, and `async with` for teardown.
- The MCP server (`npx -y microsandbox-mcp`) requires Node.js 22 or later.

## Repo status

Assessed against the requirements above on 2026-11-27, after the memory-quarantine build.

| Requirement | Status | Where |
|---|---|---|
| Agent LLM calls via Vultr Serverless Inference | Done | `backend/app/planner.py`, `backend/app/memory/judge.py`, `backend/app/memory/demo.py` |
| VM-based backend on Vultr | Done | VX1 VM in AMS, `45.77.138.3`, running the app under systemd |
| Vultr as orchestration layer | Done | Managed PostgreSQL holds memory state; the proxy runs on the VM |
| Sandboxes never in app process | Done | `backend/app/sandbox.py` (Microsandbox microVM, `ephemeral=True`, `destroy()` in `finally`) |
| Containment: no host secrets in sandbox | Done | Sandboxes get no `env`; the memory worker script has only the proxy URL and a session_id |
| Containment: resource limits | Done | CPU, memory, `max_duration`, exec timeout in `sandbox.py` |
| Containment: network | Done for the memory demo | Egress limited to the proxy's IP and port (`tests/test_egress_integration.py`) |
| Containment tests on a KVM host | Done | 6 containment and 1 egress integration test pass on the VM |
| Public web app | Done, HTTP only | `http://45.77.138.3:8000/` (Pattern A), `/ui` (review, token required) |
| Public demo URL | Done, HTTP only | Same host. HTTPS not set up |
| Demo: naive vs gated | Done | Results in `docs/memory-quarantine.md` |
| Recorded demo video with a containment moment | Not done | Your side |
| Architecture and use-case write-up | Partly done | `README.md`, `docs/memory-quarantine.md` |
| Ed25519 receipts, eval.py | Not done | Deferred; see `docs/memory-quarantine.md` |

## Pointers

- Event page: https://luma.com/stockholm-nn3n?tk=7BTEYO
- Repo README: `README.md`
- Env template: `.env.example`
