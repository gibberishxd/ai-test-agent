import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    include: ["**/*.test.ts"],
    exclude: ["node_modules/**", "e2e/**", "lib/generated/**"],
    // Creates a throwaway `agent_web_test` database for *.db.test.ts (skipped if Postgres is down).
    globalSetup: ["test/global-setup.ts"],
    setupFiles: ["test/use-test-db.ts"],
  },
});
