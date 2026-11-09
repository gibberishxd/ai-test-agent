import { execSync } from "node:child_process";
import { config } from "dotenv";
import pg from "pg";

const TEST_DB = "agent_web_test";

/**
 * Runs once before all tests: creates a fresh `agent_web_test` database and applies the Prisma
 * migrations, so database tests run against the real schema. If Postgres isn't reachable the
 * database tests skip, unless REQUIRE_DB=1 (CI), where that's a failure.
 */
export default async function setup() {
  config({ path: "../../.env", quiet: true });
  const base = process.env.DATABASE_URL ?? "postgresql://agent:agent@localhost:5432/agent";
  const admin = new pg.Client({ connectionString: base });
  try {
    await admin.connect();
  } catch (error) {
    if (process.env.REQUIRE_DB === "1") throw error;
    console.warn("[db tests] Postgres not reachable: database tests will be skipped (npm run db:up)");
    return;
  }
  await admin.query(`DROP DATABASE IF EXISTS ${TEST_DB} WITH (FORCE)`);
  await admin.query(`CREATE DATABASE ${TEST_DB}`);
  await admin.end();

  const url = new URL(base);
  url.pathname = `/${TEST_DB}`;
  execSync("npx prisma migrate deploy", { env: { ...process.env, DATABASE_URL: url.toString() }, stdio: "ignore" });
  process.env.TEST_DATABASE_URL = url.toString();
}
