# frontend/

Owner: Frontend agent. Writes only inside `frontend/`. Read-only inputs: [../contracts/openapi.yaml](../contracts/openapi.yaml), [../contracts/receipt.schema.json](../contracts/receipt.schema.json), [../contracts/fixtures/](../contracts/README.md). Root rules: [../AGENTS.md](../AGENTS.md). The record lives at the repo root.

API: `PUBLIC_API_MODE=mock|live` (default mock, serves ../contracts/fixtures via relative imports; SvelteKit 3 has no `$lib`/`$env`, use `#lib/...` and `import.meta.env`), `PUBLIC_API_BASE`, reviewer token from sessionStorage or `PUBLIC_REVIEWER_TOKEN`. Client in `src/lib/api/`, wire-rule crypto in `src/lib/crypto/`.

Stack: SvelteKit (Svelte 5), pnpm, Tailwind CSS v4, Ark UI, ESLint 10 + Prettier, Terrazzo tokens. Type: App.

## Commands
```bash
pnpm install
pnpm run dev            # dev server, port 5173; app at http://localhost:5173/ui
pnpm run build          # static SPA into build/ (adapter-static, base /ui; FastAPI mounts it)
pnpm run api:types      # regenerate src/lib/api/schema.d.ts from ../contracts/openapi.yaml
pnpm run test:e2e       # Playwright smoke (mock data)
pnpm run test:a11y      # axe checks
pnpm run check:unified  # lint, format, types, tests, tokens
pnpm run check:full     # adds build and e2e
pnpm run tokens:build   # after editing tokens/*.json
```

## Invariants
1. Run `pnpm run check:unified` after changes; fix failures before reporting done. New logic leaves a test or self-check.
2. Style with semantic tokens only; no raw colours, arbitrary values or primitives. Edit tokens/, then run tokens:build.
3. Minimal diffs: reuse house components > platform > installed deps. Grep callers before editing shared code.
4. Ask before destructive actions (deletions, drops, force pushes). Never cut validation, error handling, security or accessibility.
5. Never read, print or commit .env* or key files; add no suppression comments or skipped tests to make a check pass.

## Read first
1. [STATE.md](../.agents/context/STATE.md): now; every unverified item says `closed when:`.
2. [LEARNINGS.md](../.agents/context/LEARNINGS.md): gotchas; search before debugging.
3. [DECISIONS.md](../.agents/context/DECISIONS.md): grep the Index; open an entry for its reasons.
On demand: [SPECS.md](../.agents/context/SPECS.md) for what a capability does (openspec/specs/); the code and tests win, so fix a spec you find wrong. End a session with the close-session skill; the record check holds the budgets.

## Read when
| Task | File |
| :--- | :--- |
| Touching UI, styling or components | [UI.md](../.agents/context/UI.md), [DESIGN.md](DESIGN.md) |
| Changing structure or adding a feature | [ARCHITECTURE.md](../.agents/context/ARCHITECTURE.md) |
| Coding standards or anti-overengineering | [CODE.md](../CODE.md) |
| Stack, versions, install steps | [STACK.md](../.agents/context/STACK.md) |
| Editing design tokens | [tokens/README.md](tokens/README.md) |
