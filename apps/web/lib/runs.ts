/**
 * Reading and writing runs. The web app's only link to the worker is these rows: it inserts a
 * "queued" run, the worker claims it and writes steps, bugs, cost and status back.
 *
 * Every function takes the workspaceId and filters by it, and runs inside that workspace
 * (lib/tenant-db.ts), so Postgres itself keeps one workspace from another's runs.
 */
import { inTenant, tenantDb, type Tx } from "@/lib/tenant-db";
import { can } from "@/lib/roles";
import { usableModel } from "@/lib/model-configs";
import { quotaError, visitorRateLimitError, visitorTargetError } from "@/lib/limits";
import { isDemoTarget, parseRunInput, type FieldErrors, type RunInput } from "@/lib/targets";
import type { RequestContext } from "@/lib/workspace";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID.test(value);
}

/** Set by the public API: the key that started the run, and budgets that lower the worker's. */
export type RunExtras = { apiKeyId?: string | null; maxSteps?: number | null; maxSeconds?: number | null };

/**
 * Insert a queued run. The database writes its "run.started" audit row (trigger runs_audit),
 * with the actor and metadata the transaction set (inTenant's userId and audit).
 */
export async function createRun(
  tx: Tx,
  workspaceId: string,
  userId: string | null,
  input: RunInput,
  modelConfigId: string | null = null,
  extras: RunExtras = {},
) {
  return tx.run.create({
    data: {
      workspaceId,
      createdById: userId,
      targetUrl: input.targetUrl,
      mode: input.mode,
      focus: input.focus,
      modelConfigId,
      apiKeyId: extras.apiKeyId ?? null,
      maxSteps: extras.maxSteps ?? null,
      maxSeconds: extras.maxSeconds ?? null,
    },
  });
}

export type StartResult =
  | { ok: true; id: string }
  | { ok: false; status: number; errors: FieldErrors };

/**
 * Every check in front of a new run, in one place: input, visitor rules, quota. The worker
 * repeats the safety-relevant ones (it's the security boundary); these give clear messages.
 *
 * The quota is checked and the run inserted in one transaction: consume_quota (a database
 * function) locks the workspace row first, so two requests for the same workspace run one
 * after the other and the second counts the first one's run. Without the lock, a burst of
 * requests would each see "one run left" and all get through.
 */
export async function startRun(
  context: RequestContext,
  body: { targetUrl?: unknown; mode?: unknown; focus?: unknown; modelConfigId?: unknown },
  ip: string,
  extras: RunExtras = {},
): Promise<StartResult> {
  // Viewers read; they don't start runs. (Visitors have no role and may try the demo, below.)
  if (context.signedIn && context.role && !can(context.role, "run.start")) {
    return { ok: false, status: 403, errors: { targetUrl: "Viewers can't start runs. Ask an admin for the member role." } };
  }
  const parsed = parseRunInput(body, await verifiedOrigins(context.workspaceId));
  if (!parsed.ok) return { ok: false, status: 400, errors: parsed.errors };
  const input = parsed.value;

  // A workspace model must be this workspace's own and have passed Test connection; without
  // one, the worker's own (server default) model runs.
  const modelConfigId = typeof body.modelConfigId === "string" && body.modelConfigId ? body.modelConfigId : null;
  if (modelConfigId) {
    const usable = isUuid(modelConfigId)
      ? await usableModel(context.workspaceId, modelConfigId)
      : ({ ok: false, error: "Choose one of your workspace's models." } as const);
    if (!usable.ok) return { ok: false, status: 400, errors: { model: usable.error } };
  }

  if (!context.signedIn) {
    const targetError = visitorTargetError(isDemoTarget(input.targetUrl));
    if (targetError) return { ok: false, status: 403, errors: { targetUrl: targetError } };
  }

  const audit: Record<string, string> = extras.apiKeyId ? { ip, apiKeyId: extras.apiKeyId } : { ip };
  return inTenant({ workspaceId: context.workspaceId, userId: context.userId, audit }, async (tx): Promise<StartResult> => {
    const [quota] = await tx.$queryRaw<{ allowed: boolean; used: number; quota: number }[]>`
      SELECT * FROM consume_quota(${context.workspaceId}::uuid)`;

    if (!context.signedIn) {
      const recent = await tx.auditLog.count({
        where: {
          workspaceId: context.workspaceId,
          action: "run.started",
          createdAt: { gte: new Date(Date.now() - 60 * 60 * 1000) },
          metadata: { path: ["ip"], equals: ip },
        },
      });
      const limitError = visitorRateLimitError(recent);
      if (limitError) return { ok: false, status: 429, errors: { targetUrl: limitError } };
    }

    const overQuota = quota.allowed ? null : quotaError(quota.used, quota.quota);
    if (overQuota) return { ok: false, status: 429, errors: { targetUrl: overQuota } };

    const run = await createRun(tx, context.workspaceId, context.userId, input, modelConfigId, extras);
    return { ok: true, id: run.id };
  });
}

/** Origins (https://host) of this workspace's verified domains. */
export async function verifiedOrigins(workspaceId: string): Promise<string[]> {
  const domains = await tenantDb(workspaceId).domain.findMany({
    where: { workspaceId, verifiedAt: { not: null } },
  });
  return domains.flatMap((d) => [`https://${d.hostname}`, `http://${d.hostname}`]);
}

/** A run with its steps and bugs, or null if it doesn't exist in this workspace. */
export async function getRun(workspaceId: string, id: string) {
  if (!isUuid(id)) return null;
  return tenantDb(workspaceId).run.findFirst({
    where: { id, workspaceId },
    include: {
      steps: { orderBy: { index: "asc" } },
      bugs: { orderBy: { createdAt: "asc" } },
    },
  });
}

export async function listRuns(workspaceId: string, take = 50) {
  return tenantDb(workspaceId).run.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "desc" },
    take,
  });
}

/** Ask the worker to stop. It checks the flag between steps; a queued run just never starts. */
export async function requestStop(workspaceId: string, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const queued = await tenantDb(workspaceId).run.updateMany({
    where: { id, workspaceId, status: "queued" },
    data: { status: "stopped", stopRequested: true, finishedAt: new Date() },
  });
  if (queued.count > 0) return true;
  const running = await tenantDb(workspaceId).run.updateMany({
    where: { id, workspaceId, status: "running" },
    data: { stopRequested: true },
  });
  return running.count > 0;
}

export type RunDetail = NonNullable<Awaited<ReturnType<typeof getRun>>>;
export type RunRow = Awaited<ReturnType<typeof listRuns>>[number];
