# Tokens

DTCG JSON is the source of truth; Terrazzo (`tz`) builds `src/styles/` from it. Never edit `src/styles/*`.

1. Components use semantic or component tokens only; primitives stay inside tokens/.
2. Every semantic token has a `$description` saying when to use it.
3. Names are kebab-case; colour names follow the shadcn contract (background, foreground, primary, muted, ring ...).
4. Change a value by editing the JSON, then run the `tokens:build` script. `tokens:check` fails when the CSS is stale.
5. Retire a token with `$deprecated` and an alias; do not delete it.
6. Layout: primitive/ raw scales, semantic/ roles, component/ sizes, themes/ light and dark colours.
