import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.pw.ts", // .pw.ts keeps Vitest from collecting these specs
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173" },
  webServer: {
    command: "pnpm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
