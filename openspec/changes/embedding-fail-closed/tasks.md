## 1. Contracts (Coordinator)
- [ ] 1.1 openapi.yaml 0.3.0: add embedding_unavailable to RuleFlag and x-rulebook (FAIL_CLOSED, weight 0)
- [ ] 1.2 README gate notes; regenerate fixtures; check_contracts.py expects 14 flags
- [ ] 1.3 Add DECISIONS D7 (and Index row); update STATE and the Execution Plan flag count to 14

## 2. Infra
- [ ] 2.1 .env.example: add EMBEDDING_TIMEOUT_S=5, remove EMBEDDING_FAIL_CLOSED

## 3. Backend
- [ ] 3.1 gate.py: embedding_ok input; embedding_unavailable flag
- [ ] 3.2 Route: single embedding call with timeout; NULL embedding on failure
- [ ] 3.3 Tests: timeout scenario, NULL-embedding tombstone skipped, similarity 0.91 hits

## 4. Frontend
- [ ] 4.1 Badge label for embedding_unavailable

## 5. Tuning
- [ ] 5.1 Run eval.py benign set; record the tuned POISON_SIMILARITY_THRESHOLD in LEARNINGS.md
