<!-- generated from stack.json sha256:60bd9c365b61badcaf30fc8ccde2bfcfce21ca27169e5aced764b63216cf3f7b -->
# Stack

Resolved from stack-catalog.json (refreshed 2026-10-07). Edit stack.json, never this table.

| Layer | Choice | Why |
| :--- | :--- | :--- |
| Package manager | pnpm 12.10.1 | Strict, fast, best for monorepos. |
| Framework | SvelteKit (Svelte 5) 3.0.1 | Small bundles, simple reactivity, full-stack app framework. |
| Styling | Tailwind CSS v4 4.3.3 | Tokens flow into @theme; required by shadcn-style kits and the UI lint. |
| Kit | Ark UI 5.39.3 | Headless state-machine components across frameworks (package suffix varies by framework). |
| Lint and format | ESLint 10 + Prettier | Largest plugin ecosystem; hosts the UI lint natively. |
| Tokens | Terrazzo (DTCG, Tailwind v4 plugin, built-in lint) | Verified end to end: Tailwind v4 plugin, a11y/min-contrast lint, DTCG Resolver themes. |
| Unit tests | Vitest 5.0.3 | |
| Browser tests | Playwright snapshots + axe 1.63.0 | |
| Host | Host later | |
| Backend | Frontend only | |

Fonts: title Geist, content Geist, mono Geist Mono, display Geist. Icons: lucide.

## Setup steps
1. Install: pnpm install
2. Dependencies: pnpm add tailwindcss @ark-ui/svelte @fontsource-variable/geist @fontsource-variable/geist-mono @lucide/svelte
3. Dev dependencies: pnpm add -D svelte-check typescript@6 eslint prettier @tailwindcss/vite vitest @playwright/test@1.65.0 @axe-core/playwright playwright-core@1.65.0 @terrazzo/cli @terrazzo/plugin-css @terrazzo/plugin-tailwind
4. Normalize generated files once: pnpm run format, then pnpm run check:unified
5. Browsers: using the Playwright already installed on this machine (C:\Users\soke\AppData\Local\ms-playwright); @playwright/test is pinned to 1.65.0 to match it
6. Build the tokens once: pnpm run tokens:build (writes src/styles/tokens.css, theme.css and fluid.css)
7. Check that src/styles/index.css is imported once from the root layout and the Tailwind Vite plugin is registered (sk-init wires Astro, SvelteKit and Vite apps itself; other frameworks need it by hand)
