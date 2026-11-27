# Coding Standards

Referenced by `AGENTS.md`. These standards apply to all code changes in this workspace.

---

## 1. Minimal Complete Engineering (Anti-Overengineering)

- **Precedence ladder:** Solve tasks with the first working tier:
  1. Omit unasked options, abstractions, wrappers, and config.
  2. Reuse existing project components, helpers, and patterns.
  3. Use language standard library and platform APIs before reaching outward.
  4. Use already-installed dependencies. Never add a dependency for a trivial task.
- **Blast radius and root cause:** Before modifying shared code or fixing bugs, grep every caller across the codebase. Fix the root cause once at the source; update all affected callers, tests, and fixtures.
- **Surgical diffs:** Shortest readable diff wins. Prefer editing existing files; preserve existing structure and comments; delete before adding.
- **Measure first:** Time `typecheck`, unit tests, and `build` once (`check.mjs` prints per-step timings) before optimizing tooling or splitting build steps.
- **Self-checks:** Any new non-trivial logic (branches, parsers, calculations, state machines, security) requires a unit test or an assert-based self-check. Trivial changes need none.
- **Preserved boundaries:** Never remove trust-boundary validation, error handling that prevents data loss, security checks, or accessibility attributes.
- **Shortcut tagging:** Mark deliberate limits or temporary compromises with `shortcut: <limit>, <when to upgrade>`. Report skipped edge cases or unverified risks in your closing statement.

---

## 2. Code Quality and Craft

- **One component per file:** Separate concerns cleanly (structure, style, logic). Split oversized page or feature components along clean domain boundaries so independent agents can work in parallel without merge conflicts, while avoiding tiny speculative wrapper files.
- **No speculative abstractions:** Code for today's requirements; never build for hypothetical future needs.
- **Token discipline:** Colors, spacing, typography, and motion must consume design tokens; never hardcode hex values or raw dimensions.
- **Semantic HTML:** Use native elements (`<button>`, `<dialog>`, `<nav>`, `<details>`) over custom clickable containers.

---

## 3. TypeScript Invariants

- Strict mode enabled; no `@ts-ignore` without a justification comment.
- Never use `any`. Use `unknown` and narrow with type guards.
- Prefer `interface` over `type` for object shapes unless unions are needed.
- Exhaustive switch statements with `never` for unreachable cases.
- Avoid enums; use `as const` objects or union types.

---

## 4. Hard Constraints

- Never modify lockfiles, `package.json`, or CI configs without explicit approval.
- Never commit secrets, `.env` files, or private tokens.
- When behavior changes or is retired, update or delete obsolete tests in the same commit.
- Ask before destructive actions (deletions, database resets, force pushes).
