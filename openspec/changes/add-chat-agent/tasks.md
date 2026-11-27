## 1. Contracts (Coordinator)
- [x] 1.1 openapi.yaml 0.2.3: `/chat/sessions`, `/chat/{chat_id}/messages` (SSE), `/chat/runs/{run_id}/log`, Chat* schemas
- [x] 1.2 fixtures `chat_session.json`, `chat_stream.json`; check_contracts validates order, indexes and remember verdicts
- [x] 1.3 DECISIONS D10, STATE, AGENTS invariant 1

## 2. Backend
- [x] 2.1 `sandbox/chat_agent.py`: stdlib agent loop over the broker protocol; page text extraction inside the sandbox
- [x] 2.2 `app/chat/`: host broker, tool executors (browse, remember, recall, place_order, send_email), model call with tool definitions, step and time caps
- [x] 2.3 `app/routes/chat.py`: create chat, SSE message stream, run log; chat_busy, chat_not_found, sandbox_busy, database_missing
- [x] 2.4 Offline tests: event order, taint on browse, remember verdicts, send_email refused, order simulated, step_limit, timeout; ruff

## 3. Frontend
- [x] 3.1 SSE client (fetch + ReadableStream) and mock replay of chat_stream.json
- [x] 3.2 `/chat` page replaces the Crawl nav tab: transcript, composer, live step timeline, verdict badges linking to the review queue
- [x] 3.3 check:unified, a11y and e2e smoke

## 4. Infra
- [x] 4.1 .env.example: CHAT_MODEL, CHAT_TIMEOUT_S, CHAT_MAX_STEPS
