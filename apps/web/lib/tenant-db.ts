/**
 * The only way the web app reaches workspace data (run 4, J5; every query since run 5, K3).
 *
 * Every query runs in a transaction that first does
 *   SELECT set_config('app.workspace_id', <id>, true)    -- "true": for this transaction only
 *        , set_config('app.user_id', <user>, true)          -- who acts (the audit trigger reads it)
 *        , set_config('app.audit_metadata', <json>, true)   -- extra audit context (visitor IP…)
 *   SET LOCAL ROLE app_tenant                              -- the role the RLS policies apply to
 * so Postgres itself hides every other workspace's rows, even if a query forgets its
 * "WHERE workspace_id = …", and writes the audit log with the right actor.
 *
 * The app connects as ata_web, which can't read tenant rows at all without this (it isn't a
 * superuser and doesn't bypass row-level security). The few things that must happen before a
 * workspace is known go through narrow database functions (lib/system-db.ts).
 */
import { db } from "@/lib/db";

export type Tx = Parameters<Parameters<typeof db.$transaction>[0]>[0];

export type TenantContext = {
  workspaceId: string;
  /** The signed-in user acting, if any: recorded as the actor in the audit log. */
  userId?: string | null;
  /** Extra context the audit log should keep (for example the visitor's IP). Never secrets. */
  audit?: Record<string, string>;
};

const asContext = (ctx: string | TenantContext): TenantContext => (typeof ctx === "string" ? { workspaceId: ctx } : ctx);

function enter(client: Tx | typeof db, ctx: TenantContext) {
  return [
    client.$executeRaw`SELECT set_config('app.workspace_id', ${ctx.workspaceId}, true),
                              set_config('app.user_id', ${ctx.userId ?? ""}, true),
                              set_config('app.audit_metadata', ${JSON.stringify(ctx.audit ?? {})}, true)`,
    client.$executeRawUnsafe("SET LOCAL ROLE app_tenant"),
  ] as const;
}

/** A client whose every query runs inside the workspace (one short transaction per query). */
export function tenantDb(ctx: string | TenantContext) {
  const context = asContext(ctx);
  return db.$extends({
    name: "tenant",
    query: {
      $allModels: {
        async $allOperations({ args, query }) {
          const [, , result] = await db.$transaction([...enter(db, context), query(args)]);
          return result;
        },
      },
    },
  });
}

/** Several statements in one transaction inside the workspace (reads that must agree, writes). */
export async function inTenant<T>(ctx: string | TenantContext, fn: (tx: Tx) => Promise<T>): Promise<T> {
  const context = asContext(ctx);
  return db.$transaction(async (tx) => {
    for (const statement of enter(tx, context)) await statement;
    return fn(tx);
  });
}

/** The workspace id of a scope given as an id or a context. */
export function workspaceOf(scope: string | TenantContext): string {
  return typeof scope === "string" ? scope : scope.workspaceId;
}
