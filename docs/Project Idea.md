# Memory quarantine for AI agents

## The idea

Persistent agent memory is an active 2026 attack target. In July 2026, MemGhost showed a single crafted email planting stealthy memories in Hermes Agent, OpenClaw, and Claude Code SDK, bypassing 91.6% of input filters and 93.5% of behavior monitors. OWASP added Memory and Context Poisoning as `ASI06` in its 2026 Agentic Top 10, and A-MemGuard (Oct 2025) showed LLM detectors miss 66% of poisoned entries.

Sandboxes wipe after each task, while memory persists across sessions. Because model filters miss most attacks, deterministic code gates every memory write by session provenance, freezes tainted entries before future sessions load them, routes them to an isolated judge model to explain, and waits for human approval.

## Solution

1. A sandboxed B2B Sales / Deal Desk assistant runs in a Vultr Microsandbox with zero DB credentials. Both external reads (`POST /proxy/read`) and memory calls (`POST /proxy/memory/write`, `GET /proxy/memory/active`) pass through a host-side FastAPI Memory Proxy using a host-minted `session_id`, so a compromised sandbox cannot spoof `source='user'`.
2. Any session that reads an email or web page gets sticky session taint across all turns. Code strips zero-width and bidi characters from an inspection copy (Stage 0; the hash covers the raw bytes), evaluates the 13-flag deterministic rulebook, freezes tainted writes (`HTTP 202`, `quarantined`), saves the incident state in Managed PostgreSQL, and exits the microVM cleanly.
3. An isolated judge model on Serverless Inference (separate from the worker, with no raw session access) reads only the frozen content, provenance, and rule flags, returning strict JSON (`summary`, `risk_level`, `recommended_action`, `indicators`). The judge explains and can raise review priority; it never changes a verdict.
4. A reviewer opens the Quarantine Review UI (`GET /ui`), inspects session-grouped rows alongside raw source snippets, rule verdicts, and judge notes, and clicks `Purge` or `Override` per row (`BLOCKED` and `FAIL_CLOSED` overrides require a typed reason). Rows are sorted by a deterministic `risk_score` (0-100) plus a +15 boost when the judge recommends purge at high or critical risk.
5. Every step appends to a `SHA-256` hash chain (`audit_events`) and saves an Ed25519-signed receipt to Vultr Object Storage; future sessions query only `active` rows.

### Deterministic gate rules

Combines PerMIT's finite gate (trust only user inputs and gate-confirmed hashes), MemSentry's pre-commit routing (`Accept`, `Review`, `Quarantine`, which caught 100% of external quarantine threats in its benchmark), and session provenance grouping:

Precedence: `FAIL_CLOSED` > `BLOCKED` > `NEEDS_REVIEW` > `ALLOW`. Full rulebook, weights and Stage 0 in [Execution Plan.md](Execution%20Plan.md#threat-model-and-detection) and [contracts/README.md](../contracts/README.md).

| Verdict | Deterministic rule in code (rule flags) | Action |
| --- | --- | --- |
| `ALLOW` | Zero external reads in session, no rule hits, insert-only, at most 3 writes | `HTTP 201`, promoted to `memories` (`risk_score` 0) |
| `NEEDS_REVIEW` | `tainted_session`, `immediate_write_after_read`, `write_burst` (more than 3 writes in one `session_id`), `overwrite_attempt` | `HTTP 202`, frozen for per-row review; override reason optional |
| `BLOCKED` | `imperative_directive` (aimed at an outbound action or policy override, not plain preferences), `external_email` and `external_url` (not on `ALLOWLISTED_DOMAINS`), `sensitive_tool` (`send_email`), `canary_overlap`, `poison_similarity` to a purged tombstone (never pre-seeded from `eval.py`) | `HTTP 202`, locked against auto-promotion; `Override` requires a typed reason |
| `FAIL_CLOSED` | `missing_provenance`, `invalid_schema`, or post-freeze `judge_failed` (escalates `NEEDS_REVIEW`; a `BLOCKED` row stays `BLOCKED`) | `HTTP 202`, `risk_score` floor 85; `Override` requires a typed reason |

### Storage options (team decision)

Records store `content`, server-assigned `source`, `session_id`, `source_ref`, `payload_hash`, `verdict`, `risk_score`, `rule_flags`, `judge_note`, `override_reason`, `receipt_uri`, and embedding, paired with `audit_events` and Object Storage receipts (`Purge` wipes `content` while keeping `payload_hash` as a tombstone in DB and the signed receipt):

| Option | How isolation works | Trade-off |
| --- | --- | --- |
| A: Single `memories` table | Adds a `status` column (`active`, `quarantined`, `purged`); every `pgvector` query filters `WHERE status = 'active'` | Fastest to build; every read path must enforce the filter |
| B: Separate `quarantine_queue` table | Active rows stay in `memories`; tainted writes move to `quarantine_queue` until `Override` | Stronger isolation; active queries never touch quarantined rows |

## Honeypot demo (team option)

One concrete option for the team to evaluate is a B2B Sales / Deal Desk assistant protecting confidential floor pricing (avoiding purchasing, which Errand already covered). The team can keep this scenario or swap in another single buyer with a clear costly leak.

### What the honeypot is

Instead of waiting for real attackers, we run a self-contained test trap inside our environment with three pieces:

- Seeded poisoned sources: mock prospect emails and web pages carrying hidden instructions (such as forwarding deal pricing to an external address).
- Canary secrets: fake floor-pricing sheets accessible only in Session 2 (quoting), keeping Session 1 (research) isolated from same-session leaks.
- Monitored fake `send_email` tool: logs every outbound recipient and payload to disk without sending real mail.

### How the demo runs

Both runs use the same Serverless Inference worker model and log to `GET /demo/runs`:

1. Naive baseline (`gate_mode=naive` proxy bypass): the worker reads a poisoned email in Session 1, writes the dormant instruction to memory, and leaks the canary pricing via `send_email` in Session 2.
2. Quarantined run: the proxy freezes the write on provenance and rule hits, the judge explains the payload, the reviewer purges the row in `GET /ui`, and Session 2 leaks nothing.

To measure containment and false positives, `eval.py` runs 10 seeded attacks (direct, split-write, and dormant keyword triggers) plus 6 benign look-alike notes (testing both untainted user notes and external notes that pass without hitting `BLOCKED`), reporting leak rate, benign clearance, latency, and token cost.

## Limits

Protects future sessions through the Memory Proxy; same-session tool egress, pre-existing DB rows, and untrusted text pasted by a user stay outside this gate. Sticky taint trades extra review on mixed sessions for fewer silent misses on external-content runs. All `eval.py` misses and false positives will be reported openly.

## Recommended next steps

A few decisions and checks the team may want to walk through together:

- [ ] Agree on the buyer scenario: keep the B2B Sales / Deal Desk assistant protecting floor pricing, or pick another workflow with a clear leak target.
- [ ] Choose a storage layout: Option A (`memories` table with `status` filter) or Option B (separate `quarantine_queue` table).
- [ ] Confirm the deterministic gate thresholds (such as the 3-write burst limit and domain allowlist) and the `BLOCKED` / `FAIL_CLOSED` typed override policy.
- [ ] Review the honeypot seeded emails, canary secrets, and `eval.py` attack vs. benign test mix.
- [ ] Walk through the `Read first` Vultr docs and split up work across the proxy, sandboxed agent, and Review UI.

## Vultr docs

Read first:

- [Agent sandboxing with Microsandbox](https://docs.vultr.com/how-to-set-up-agent-sandboxing-on-vultr-cloud-compute): isolates worker sessions from DB credentials.
- [Serverless Inference](https://docs.vultr.com/products/compute/serverless-inference): separate worker and judge models.
- [Managed Databases](https://docs.vultr.com/products/storage/databases): hosts memories, quarantine state, and `audit_events`.

Optional:

- [pgvector on Managed PostgreSQL](https://docs.vultr.com/ai-powered-search-with-pgvector-and-vultr-managed-database-for-postgresql): active recall and known-poison similarity checks.
- [Hermes Agent deploy guide](https://docs.vultr.com/how-to-deploy-hermes-agent-open-source-self-hosted-ai-agent): persistent-memory agent affected by MemGhost.

## Research

| Paper | Date | Technique we use |
| --- | --- | --- |
| [A-MemGuard](https://arxiv.org/abs/2510.02373) | Oct 2025 | Shows LLM detectors miss 66% of poisoned entries, motivating deterministic gating |
| [MemGhost](https://arxiv.org/abs/2607.05189) | Jul 2026 | Separates memory-read vs. memory-write controls (one email bypasses 90%+ of monitors) |
| [Trojan Hippo Bench](https://arxiv.org/abs/2605.01970) | Sep 2026 | Dormant email payloads triggered turns later on pricing or finance queries |
| [MemSentry](https://arxiv.org/abs/2609.08747) | Sep 2026 | Pre-commit deterministic routing (`Accept`, `Review`, `Quarantine`) via provenance and directive rules |
| [PerMIT](https://arxiv.org/abs/2610.28987) | Oct 2026 | Finite interface trusting only user inputs and gate-confirmed content hashes |
| [The Price of Safety](https://arxiv.org/abs/2609.22818) | Sep 2026 | Measures false-positive friction on benign tasks without attacks |

## Appendix: last time's winners

### Rubric

Started at 32/50 on the initial draft against the Nov 2026 winners; implementing the updated design and `eval.py` targets 50/50. In all three winners, code decided, the model explained, and a person approved risky steps.

| Criterion | What the winners did | Initial draft | Target with design |
| --- | --- | --- | --- |
| Code decides, model explains | Airlock's rule table sets the verdict; Errand checks the budget in code | 4/5 | 5/5 (4-state gate + `FAIL_CLOSED`) |
| Human approves the risky step | Suspicious PRs, payment actions, and orders wait for a person | 2/5 | 5/5 (`GET /ui` per-row gate + typed override) |
| One buyer, one costly job | PR review, supplier payments, purchasing | 2/5 | 5/5 (Deal Desk floor pricing) |
| Containment proven every run | Canary keys; a credential-leak probe on every supplier visit | 5/5 | 5/5 (Session 2 canary + `send_email` probe) |
| Before-and-after number | 18 of 19 verdicts right; 15 of 15 leaks vs 0 of 15 | 1/5 | 5/5 (`eval.py` 10 attacks + 6 benign) |
| Recent, named threat up front | 2025 supply-chain attacks; Oct 2026 fake-login research | 4/5 | 5/5 (MemGhost Jul 2026 + OWASP `ASI06`) |
| Receipts for every step | Per-finding receipts, signed report, hash-chained ledger | 3/5 | 5/5 (`SHA-256` chain + Ed25519 receipt) |
| Vultr beyond the minimum | Managed Postgres, Object Storage, VX1 microVMs, several models | 3/5 | 5/5 (Microsandbox, Managed PG/pgvector, multi-model Inference, Object Storage) |
| Original vs past entries | Each owned one niche | 5/5 | 5/5 (Cross-session memory quarantine) |
| Honest about limits | Airlock: "proves the harness, not the product" | 3/5 | 5/5 (Explicit proxy/egress boundaries + open `eval.py` misses) |
| Total |  | 32/50 | 50/50 |

### Winners of Vultr Agent Rush (Nov 2026)

| Place | Project | Job | Proof |
| --- | --- | --- | --- |
| 1st | [Airlock](https://lablab.build/ai-hackathons/vultr-hackathon/v3n/airlock-run-the-pr-before-you-trust-it) | Runs a stranger's PR in twin gVisor sandboxes before merge | 18 of 19 seeded attacks got the right verdict |
| 2nd | [Follow the Money](https://lablab.build/ai-hackathons/vultr-hackathon/fire-exit/follow-the-money-agents-that-trace-every-payment) | 7 agents investigate a payment run; only the Finance Director acts | $283,600 flagged across 108 payments, about $0.08 per investigation |
| 3rd | [Errand](https://lablab.build/ai-hackathons/vultr-hackathon/errand/errand-your-agent-never-sees-the-password) | Purchasing agent types a placeholder; the real password is swapped in outside the VM | Leaks: 15 of 15 with the password in the browser, 0 of 15 with Errand |
