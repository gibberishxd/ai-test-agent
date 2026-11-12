/**
 * Prints a Mermaid ER diagram of the real schema (run 5, K3): tables, columns, primary and
 * foreign keys, read from Postgres's catalog, so docs/DATABASE.md never drifts from the
 * migrations. Usage: node scripts/er-diagram.mjs [database url]  (default: DATABASE_URL).
 */
import { config } from "dotenv";
import pg from "pg";

config({ path: new URL("../../../.env", import.meta.url).pathname, quiet: true });

const client = new pg.Client({ connectionString: process.argv[2] ?? process.env.DATABASE_URL });
await client.connect();
try {
  const { rows: columns } = await client.query(`
    SELECT c.table_name, c.column_name,
           CASE WHEN c.data_type = 'USER-DEFINED' THEN c.udt_name
                WHEN c.data_type = 'ARRAY' THEN replace(c.udt_name, '_', '') || '[]'
                ELSE replace(c.data_type, ' ', '_') END AS type,
           EXISTS (SELECT 1 FROM information_schema.table_constraints t
                     JOIN information_schema.key_column_usage k USING (constraint_name, table_name)
                    WHERE t.constraint_type = 'PRIMARY KEY' AND t.table_name = c.table_name
                      AND k.column_name = c.column_name) AS pk
      FROM information_schema.columns c
      JOIN information_schema.tables t ON t.table_name = c.table_name AND t.table_schema = c.table_schema
     WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.table_name <> '_prisma_migrations'
     ORDER BY c.table_name, c.ordinal_position`);
  const { rows: keys } = await client.query(`
    SELECT con.conrelid::regclass::text AS child, con.confrelid::regclass::text AS parent,
           a.attname AS column_name, NOT a.attnotnull AS optional
      FROM pg_constraint con
      JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
     WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace
     ORDER BY 1, 3`);

  const fk = new Set(keys.map((k) => `${k.child}.${k.column_name}`));
  const out = ["erDiagram"];
  for (const k of keys) {
    // parent ||--o{ child: one parent, zero or more children; |o when the key may be null.
    out.push(`  ${k.parent} ${k.optional ? "|o" : "||"}--o{ ${k.child} : "${k.column_name}"`);
  }
  let table = null;
  for (const c of columns) {
    if (c.table_name !== table) {
      if (table) out.push("  }");
      table = c.table_name;
      out.push(`  ${table} {`);
    }
    const mark = c.pk ? " PK" : fk.has(`${c.table_name}.${c.column_name}`) ? " FK" : "";
    out.push(`    ${c.type} ${c.column_name}${mark}`);
  }
  if (table) out.push("  }");
  console.log(out.join("\n"));
} finally {
  await client.end();
}
