## 1. Contracts (Coordinator, Phase 0)
- [x] 1.1 schema.sql: verdict check, writes_since_last_read, risk_score, reason constraint for BLOCKED and FAIL_CLOSED
- [x] 1.2 openapi.yaml 0.2.0: verdicts, 13 flags, x-rulebook, risk_score, effective_priority_score, demo endpoints
- [x] 1.3 receipt.schema.json and judge.schema.json
- [x] 1.4 README rules, fixtures regenerated, check_contracts.py rulebook checks
- [x] 1.5 Specs, AGENTS.md, Project Idea, DECISIONS D5, STATE

## 2. Infra (Phase 1)
- [ ] 2.1 Mirror schema.sql into infra/sql/001_init.sql; migrate the local database
- [ ] 2.2 .env.example: ALLOWLISTED_DOMAINS, CANARY_TOKENS, POISON_SIMILARITY_THRESHOLD, EMBEDDING_TIMEOUT_S, SANDBOX_* caps, S3_REGION (no EMBEDDING_FAIL_CLOSED toggle; see embedding-fail-closed)

## 3. Backend (Phase 1)
- [ ] 3.1 models.py and gate.py per the rulebook (Stage 0, 13 flags, risk_score)
- [ ] 3.2 Routes, judge escalation, override hash check, priority sort
- [ ] 3.3 Demo runner and egress tests

## 4. Frontend (Phase 1)
- [ ] 4.1 Types, badges, risk_score, Evaluating state, priority queue
- [ ] 4.2 Purge and Override with reason rules; demo runner tab
