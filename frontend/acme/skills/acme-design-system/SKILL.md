---
name: acme-design-system
description: Applies the Acme design system to any UI work in this project (components, pages, styling, colors, type, spacing, icons, motion). Use whenever writing or reviewing UI code here.
---

# Acme design system

The system lives in `DESIGN.md` (rules and rationale) and `tokens.css` (every value). Read DESIGN.md before writing UI. These rules are not optional.

## Hard rules

1. **Tokens only.** Every color, font size, line height, spacing, radius, shadow, duration and easing comes from a token. No hex codes, no arbitrary px, no Tailwind arbitrary values like `p-[13px]`. If a value is missing, say so and stop; don't invent one.
2. **Roles before steps.** Use role tokens (`bg`, `text`, `text-muted`, `fill`, `border`, `primary`, `primary-fg`…). Raw scale steps (`primary-3`) only for their documented step job.
3. **One primary action per view** uses `primary`. Everything else is secondary (`fill`) or ghost.
4. **Type roles only:** display, h1, h2, h3, body-lg, body, label, caption, code. Never set font-size by hand.
5. **Icons: Lucide only.** Stroke 1.5px. Never import a second icon library.
6. **Components: shadcn/ui.** Extend it; don't add another component library.
7. **Nested radius:** inner = outer − padding.
8. **Both themes.** Never hardcode light-only colors; roles switch automatically with `data-theme`.
9. **Motion:** transform and opacity only, durations from tokens, respect reduced motion.

## Before you finish

- Search your diff for `#`, `rgb(`, `px` outside token files and arbitrary values. Replace each with a token.
- Check every new text color against its background in DESIGN.md's Colors table.
- Confirm no new dependency for icons or components was added.
