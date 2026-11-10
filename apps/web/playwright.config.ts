import { defineConfig } from "@playwright/test";

/**
 * End-to-end test of the main flow: web app + demo shop + worker, all real, with the worker on
 * the scripted FakeClient so the test is fast, free and deterministic. Needs Postgres
 * (`npm run db:up`). Run: npm run test:e2e
 */
export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  timeout: 180_000,
  // On CI the dev server starts cold: the very first sign-in can race its first compile.
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000", headless: true },
  webServer: [
    { command: "npm run dev", url: "http://localhost:3000", reuseExistingServer: true, timeout: 120_000 },
    {
      command: "npm run dev -w apps/demo",
      cwd: "../..",
      url: "http://localhost:5173",
      reuseExistingServer: true,
    },
    {
      // The worker has no port to wait for: it logs "ready" when it starts polling the queue.
      command: "uv run --project ../worker worker",
      // FAKE_SCRIPT: in interactive runs the scripted agent clicks the first element, then
      // finishes, so the live browser pane has a step with an outline to show.
      env: {
        LLM_PROVIDER: "fake",
        REVIEW_PAGES: "0",
        DEV_MODE: "true",
        FAKE_SCRIPT: '[["click", {"element_id": 1}], ["finish", {"summary": "done"}]]',
      },
      wait: { stderr: /ready\./ },
      timeout: 120_000,
    },
  ],
});
