import adapter from "@sveltejs/adapter-static";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";

const contracts = fileURLToPath(new URL("../contracts", import.meta.url));

export default defineConfig({
  plugins: [
    tailwindcss(),
    sveltekit({
      compilerOptions: {
        // Force runes mode for the project, except for libraries. Can be removed in svelte 6.
        runes: ({ filename }) =>
          filename.split(/[/\\]/).includes("node_modules") ? undefined : true,
      },

      // SPA build; FastAPI mounts frontend/build at /ui.
      adapter: adapter({ fallback: "index.html" }),
      paths: { base: "/ui" },
    }),
  ],
  envPrefix: ["VITE_", "PUBLIC_"],
  server: { fs: { allow: [contracts] } },
});
