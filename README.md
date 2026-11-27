# Memory Quarantine for AI Agents

Deterministic quarantine for agent memory writes on the Vultr stack. Every write passes a pure code gate (`ALLOW`, `NEEDS_REVIEW`, `BLOCKED`, `FAIL_CLOSED`, with a 0-100 `risk_score`); frozen writes wait for a human Purge or Override with Ed25519-signed receipts.

- Start here: [AGENTS.md](AGENTS.md)
- Plan: [docs/Execution Plan.md](docs/Execution%20Plan.md) (includes the exploit model and rulebook)
- Contracts: [contracts/](contracts/README.md); specs: [openspec/specs/](openspec/specs/)
