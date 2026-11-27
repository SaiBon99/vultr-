import { defineConfig } from "@terrazzo/cli";
import css from "@terrazzo/plugin-css";
import tailwind from "@terrazzo/plugin-tailwind";

export default defineConfig({
  tokens: ["./tokens/tokens.resolver.json"],
  outDir: "./src/styles/",
  plugins: [
    css({
      filename: "tokens.css",
      permutations: [
        { input: { theme: "light" }, prepare: (c) => `:root {\n${c}\n}` },
        { input: { theme: "dark" }, prepare: (c) => `.dark {\n${c}\n}` },
      ],
    }),
    tailwind({
      template: "../../tokens/tailwind.template.css",
      filename: "theme.css",
      defaultTheme: { theme: "light" },
      theme: {
        color: ["color.*"],
        font: ["font.*"],
        spacing: ["spacing.*"],
        radius: ["radius.*"],
        ease: ["ease.*"],
      },
    }),
  ],
  lint: {
    rules: {
      "core/consistent-naming": ["error", { format: "kebab-case" }],
      "core/descriptions": ["error", { ignore: ["primitive.**"] }],
      "a11y/min-contrast": [
        "error",
        {
          level: "AA",
          pairs: [
            { foreground: "color.foreground", background: "color.background" },
            { foreground: "color.card-foreground", background: "color.card" },
            {
              foreground: "color.popover-foreground",
              background: "color.popover",
            },
            {
              foreground: "color.primary-foreground",
              background: "color.primary",
            },
            {
              foreground: "color.secondary-foreground",
              background: "color.secondary",
            },
            { foreground: "color.muted-foreground", background: "color.muted" },
            {
              foreground: "color.muted-foreground",
              background: "color.background",
            },
            {
              foreground: "color.accent-foreground",
              background: "color.accent",
            },
            {
              foreground: "color.destructive-foreground",
              background: "color.destructive",
            },
            {
              foreground: "color.success-foreground",
              background: "color.success",
            },
            { foreground: "color.info-foreground", background: "color.info" },
            {
              foreground: "color.warning-foreground",
              background: "color.warning",
            },
            {
              foreground: "color.ring",
              background: "color.background",
              largeText: true,
            },
            {
              foreground: "color.primary",
              background: "color.background",
              largeText: true,
            },
          ],
        },
      ],
    },
  },
});
