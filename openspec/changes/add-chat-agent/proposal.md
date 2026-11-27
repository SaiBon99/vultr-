# Add a shopping chat agent (replaces the Crawl tab)

## Why
A one-shot crawl does not show why memory quarantine matters. A chat where a reviewer asks the agent to order something from a website does: the agent reads an untrusted product page, the page tries to plant a standing instruction, and the gate freezes it while the order still goes through. Multi-turn recall then shows the poisoned note never comes back.

## What Changes
- `POST /chat/sessions` (ReviewerToken) creates a chat bound to one quarantined memory session. History stays on the host.
- `POST /chat/{chat_id}/messages` runs one agent per message in the /crawl Docker sandbox (same isolation, shares the D8 2-run cap) and streams `ChatEvent`s as SSE: run, step*, then reply+done or error.
- Host-brokered tools only: `browse` (public-target guard, any public URL, taints the session), `remember` (gate via `app/memory_store.write_memory`), `recall` (memories only), `place_order` (always simulated, `SIM-` ids), `send_email` (always refused, contained egress).
- Per-message cap `CHAT_TIMEOUT_S` (default 90) and `CHAT_MAX_STEPS` (default 8) (D10). Memory and CPU caps unchanged.
- `GET /chat/runs/{run_id}/log`: NDJSON transcript under `logs/chat/` (wire rule 6).
- Frontend: `/ui/chat` replaces the Crawl tab; `/crawl` stays in the API.
- Contracts `openapi.yaml` 0.2.3, additive; fixtures `chat_session.json`, `chat_stream.json`.

## Capabilities
- New: `chat-agent`.

## Out of scope
- Real purchases, payment, accounts or carts. Checkout is always simulated.
- Persisting chat history across server restarts.
- Removing `POST /crawl`.

## Impact
- contracts/: paths `/chat/*`, schemas `Chat*`, tag `chat`; check_contracts validates the stream and recomputes remember verdicts.
- backend/: `app/chat/` (broker loop, tools, model with tool calls), `app/routes/chat.py`, `sandbox/chat_agent.py`, settings `CHAT_MODEL`, `CHAT_TIMEOUT_S`, `CHAT_MAX_STEPS`; offline tests with fake runner, fake model, fake resolver.
- frontend/: `src/routes/chat/`, SSE client in `src/lib/api/`, mock replay of `chat_stream.json`, nav tab.
- infra/: `.env.example` gains the three CHAT_* settings.
