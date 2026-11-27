---
name: frontend
description: "Develop, verify, and deploy frontend: stack commands, the unified check, design tokens and context docs."
---

# frontend Project Skill

Use when changing code in this project. Stack: SvelteKit (Svelte 5), pnpm, Tailwind CSS v4, Ark UI, ESLint 10 + Prettier, Terrazzo tokens.

## Workflow
1. Read AGENTS.md, then the one context doc its Read when table names for the task.
2. Make the change with semantic tokens and existing components.
3. Run `pnpm run check:unified`; fix every failure. Use `pnpm run check:full` before releases.
4. Report what changed and the check result; at the end of a session run the close-session skill.

Context docs: [.agents/context/](../../context/).
