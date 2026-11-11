import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const EXCLUDE = ["node_modules/**", "e2e/**", "lib/generated/**"];

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    // Creates a throwaway `agent_web_test` database for *.db.test.ts (skipped if Postgres is down).
    globalSetup: ["test/global-setup.ts"],
    setupFiles: ["test/use-test-db.ts"],
    projects: [
      { extends: true, test: { name: "unit", include: ["**/*.test.ts"], exclude: [...EXCLUDE, "**/*.db.test.ts"] } },
      // Database tests share one database and empty its tables: one file at a time.
      { extends: true, test: { name: "db", include: ["**/*.db.test.ts"], exclude: EXCLUDE, fileParallelism: false } },
    ],
  },
});
