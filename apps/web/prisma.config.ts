import { config } from "dotenv";
import { defineConfig } from "prisma/config";

// One .env for the whole repo, at the root.
config({ path: "../../.env", quiet: true });

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: { path: "prisma/migrations" },
  // The fallback lets `prisma generate` run where no database is configured (CI typecheck).
  datasource: { url: process.env["DATABASE_URL"] ?? "postgresql://agent:agent@localhost:5432/agent" },
});
