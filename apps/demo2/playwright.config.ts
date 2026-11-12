import { defineConfig } from "@playwright/test";

/**
 * Verifies the holdout app's planted bugs: present on the buggy build (5175), absent on the
 * clean one (5176). Run: npm run verify-bugs -w apps/demo2
 */
export default defineConfig({
  testDir: "verify",
  testMatch: "*.e2e.ts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { headless: true },
  projects: [
    { name: "buggy", use: { baseURL: "http://localhost:5175" } },
    { name: "clean", use: { baseURL: "http://localhost:5176" } },
  ],
  webServer: [
    { command: "npm run dev", url: "http://localhost:5175", reuseExistingServer: true },
    { command: "npm run dev:clean", url: "http://localhost:5176", reuseExistingServer: true },
  ],
});
