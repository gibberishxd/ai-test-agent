import { defineConfig } from "@playwright/test";

/**
 * Verifies the planted bugs: every check runs against both builds and expects the bug to be
 * present on the buggy shop (5173) and absent on the clean one (5174). Run: npm run verify-bugs
 */
export default defineConfig({
  testDir: "verify",
  testMatch: "*.e2e.ts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { headless: true },
  projects: [
    { name: "buggy", use: { baseURL: "http://localhost:5173" } },
    { name: "clean", use: { baseURL: "http://localhost:5174" } },
  ],
  webServer: [
    { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: true },
    { command: "npm run dev:clean", url: "http://localhost:5174", reuseExistingServer: true },
  ],
});
