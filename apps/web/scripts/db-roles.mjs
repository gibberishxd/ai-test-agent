/**
 * Database roles and their passwords (run 5, K3). Idempotent: run it on the admin connection
 * (DATABASE_URL) in dev (`npm run db:roles`), CI and production, after the migrations.
 *
 *   ata_owner   owns the schema; migrations can run as it on a managed database
 *   ata_web     the web app       (WEB_DATABASE_URL)
 *   ata_worker  the worker        (WORKER_DATABASE_URL)
 *
 * None is a superuser or bypasses row-level security. Passwords come from DB_OWNER_PASSWORD,
 * DB_WEB_PASSWORD and DB_WORKER_PASSWORD; a role whose variable is unset keeps its password.
 * Migrations create the roles when they run as a superuser; this script also creates them, for
 * a database where an operator runs this first and the migrations as ata_owner.
 */
import { config } from "dotenv";
import pg from "pg";

config({ path: new URL("../../../.env", import.meta.url).pathname, quiet: true });

const ROLES = [
  ["ata_owner", "DB_OWNER_PASSWORD"],
  ["ata_web", "DB_WEB_PASSWORD"],
  ["ata_worker", "DB_WORKER_PASSWORD"],
];

const ensure = (role, attributes) => `DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${role}') THEN
    CREATE ROLE ${role} ${attributes};
  END IF;
END $$`;

const client = new pg.Client({ connectionString: process.env.DATABASE_URL });
await client.connect();
try {
  await client.query(ensure("app_tenant", "NOLOGIN NOBYPASSRLS"));
  for (const [role, variable] of ROLES) {
    await client.query(ensure(role, "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"));
    const password = process.env[variable];
    if (password) {
      // ALTER ROLE can't take a bound parameter: the password is quoted as a SQL literal.
      await client.query(`ALTER ROLE ${role} WITH LOGIN PASSWORD ${client.escapeLiteral(password)}`);
      console.log(`${role}: password set`);
    } else {
      console.log(`${role}: exists (${variable} not set, password unchanged)`);
    }
  }
  await client.query("GRANT app_tenant TO ata_web, ata_worker");
  const { rows } = await client.query("SELECT current_database() AS name");
  await client.query(`GRANT CONNECT ON DATABASE ${client.escapeIdentifier(rows[0].name)} TO ata_owner, ata_web, ata_worker`);
  await client.query("GRANT USAGE, CREATE ON SCHEMA public TO ata_owner");
  await client.query("GRANT USAGE ON SCHEMA public TO ata_web, ata_worker");
} finally {
  await client.end();
}
