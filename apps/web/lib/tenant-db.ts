/**
 * A Prisma client for one workspace, with Postgres row-level security behind it (run 4, J5).
 *
 * Every query runs in its own short transaction that first does
 *   SELECT set_config('app.workspace_id', <id>, true)   -- "true": for this transaction only
 *   SET LOCAL ROLE app_tenant                           -- a role the RLS policies apply to
 * so the database itself hides every other workspace's rows, even if a query forgets its
 * "WHERE workspace_id = …". The app's own checks stay: this is the second line of defence.
 * docs/DATABASE.md explains the policies and what they cost.
 */
import { db } from "@/lib/db";

export function tenantDb(workspaceId: string) {
  return db.$extends({
    name: "tenant",
    query: {
      $allModels: {
        async $allOperations({ args, query }) {
          const [, , result] = await db.$transaction([
            db.$executeRaw`SELECT set_config('app.workspace_id', ${workspaceId}, true)`,
            db.$executeRawUnsafe("SET LOCAL ROLE app_tenant"),
            query(args),
          ]);
          return result;
        },
      },
    },
  });
}
