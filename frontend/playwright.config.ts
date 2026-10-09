import { defineConfig } from "@playwright/test";

// E2E contro lo stack Docker completo (nginx → api → worker). Lo stack va
// avviato prima: vedi «Test end-to-end» in ARCHITECTURE.md.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    channel: process.env.E2E_CHANNEL ?? undefined,
    screenshot: "only-on-failure",
  },
});
