# Embedding failure fails closed

## Why
`poison_similarity` needs an embedding of the write before the pure gate runs. Contracts 0.2.0 define no flag for an embedding call that times out or errors, and the Phase 1 plan adds `EMBEDDING_FAIL_CLOSED=false`, which would let such a write reach `ALLOW` without the known-poison check. A failed safety check must fail closed (invariant 3).

## What Changes
- New rule flag `embedding_unavailable`: verdict `FAIL_CLOSED`, weight 0, so `risk_score` takes the 85 floor. RuleFlag grows from 13 to 14.
- The proxy retries nothing: one embedding call with a short timeout (`EMBEDDING_TIMEOUT_S`, default 5). On failure the row is frozen with a NULL embedding, so it never becomes a tombstone for `poison_similarity`.
- Remove the `EMBEDDING_FAIL_CLOSED` toggle from the plan; failing closed is not configurable.
- `POISON_SIMILARITY_THRESHOLD` (0.85 cosine similarity, already in contracts/README.md) stays a config value; it is tuned so the 6 benign `eval.py` look-alikes never trip it, and the tuned value is recorded in LEARNINGS.md.

## Capabilities
- Modified: `memory-gate`.

## Impact
- contracts/: openapi.yaml 0.3.0 (RuleFlag enum and `x-rulebook`), README gate notes, fixtures regenerated, check_contracts.py flag count.
- infra/: `.env.example` gains `EMBEDDING_TIMEOUT_S` and drops `EMBEDDING_FAIL_CLOSED`.
- backend/: `gate.py` input `embedding_ok`; route sets it; test for the timeout path.
- frontend/: badge label for the new flag.
- Depends on `refine-verdicts-and-rulebook` (D5); archive that change first.
