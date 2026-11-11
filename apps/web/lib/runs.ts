/**
 * Reading and writing runs. The web app's only link to the worker is these rows: it inserts a
 * "queued" run, the worker claims it and writes steps, bugs, cost and status back.
 *
 * Every function takes the workspaceId and filters by it, so one workspace can never read or
 * change another's runs.
 */
import { db } from "@/lib/db";
import { usableModel } from "@/lib/model-configs";
import { quotaError, startOfMonth, visitorRateLimitError, visitorTargetError } from "@/lib/limits";
import { isDemoTarget, parseRunInput, type FieldErrors, type RunInput } from "@/lib/targets";
import type { RequestContext } from "@/lib/workspace";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID.test(value);
}

type Tx = Parameters<Parameters<typeof db.$transaction>[0]>[0];

/** Set by the public API: the key that started the run, and budgets that lower the worker's. */
export type RunExtras = { apiKeyId?: string | null; maxSteps?: number | null; maxSeconds?: number | null };

export async function createRun(
  workspaceId: string,
  userId: string | null,
  input: RunInput,
  meta: Record<string, string> = {},
  client: Tx | typeof db = db,
  modelConfigId: string | null = null,
  extras: RunExtras = {},
) {
  const run = await client.run.create({
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
  await client.auditLog.create({
    data: {
      workspaceId,
      userId,
      action: "run.started",
      targetUrl: input.targetUrl,
      mode: input.mode,
      runId: run.id,
      metadata: meta,
    },
  });
  return run;
}

export type StartResult =
  | { ok: true; id: string }
  | { ok: false; status: number; errors: FieldErrors };

/**
 * Every check in front of a new run, in one place: input, visitor rules, quota. The worker
 * repeats the safety-relevant ones (it's the security boundary); these give clear messages.
 *
 * The limits are counted and the run is inserted in one transaction that first locks the
 * workspace row (SELECT ... FOR UPDATE). Two requests for the same workspace therefore run one
 * after the other: the second counts the first one's run. Without the lock, a burst of
 * requests would each see "one run left" and all get through.
 */
export async function startRun(
  context: RequestContext,
  body: { targetUrl?: unknown; mode?: unknown; focus?: unknown; modelConfigId?: unknown },
  ip: string,
  extras: RunExtras = {},
): Promise<StartResult> {
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

  return db.$transaction(async (tx): Promise<StartResult> => {
    const locked = await tx.$queryRaw<{ monthly_run_quota: number }[]>`
      SELECT monthly_run_quota FROM workspaces WHERE id = ${context.workspaceId}::uuid FOR UPDATE`;
    if (locked.length === 0) throw new Error(`workspace ${context.workspaceId} not found`);

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

    const used = await tx.run.count({
      where: { workspaceId: context.workspaceId, createdAt: { gte: startOfMonth(new Date()) } },
    });
    const overQuota = quotaError(used, locked[0].monthly_run_quota);
    if (overQuota) return { ok: false, status: 429, errors: { targetUrl: overQuota } };

    const meta: Record<string, string> = extras.apiKeyId ? { ip, apiKeyId: extras.apiKeyId } : { ip };
    const run = await createRun(context.workspaceId, context.userId, input, meta, tx, modelConfigId, extras);
    return { ok: true, id: run.id };
  });
}

/** Origins (https://host) of this workspace's verified domains. */
export async function verifiedOrigins(workspaceId: string): Promise<string[]> {
  const domains = await db.domain.findMany({
    where: { workspaceId, verifiedAt: { not: null } },
  });
  return domains.flatMap((d) => [`https://${d.hostname}`, `http://${d.hostname}`]);
}

/** A run with its steps and bugs, or null if it doesn't exist in this workspace. */
export async function getRun(workspaceId: string, id: string) {
  if (!isUuid(id)) return null;
  return db.run.findFirst({
    where: { id, workspaceId },
    include: {
      steps: { orderBy: { index: "asc" } },
      bugs: { orderBy: { createdAt: "asc" } },
    },
  });
}

export async function listRuns(workspaceId: string, take = 50) {
  return db.run.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "desc" },
    take,
  });
}

/** Ask the worker to stop. It checks the flag between steps; a queued run just never starts. */
export async function requestStop(workspaceId: string, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const queued = await db.run.updateMany({
    where: { id, workspaceId, status: "queued" },
    data: { status: "stopped", stopRequested: true, finishedAt: new Date() },
  });
  if (queued.count > 0) return true;
  const running = await db.run.updateMany({
    where: { id, workspaceId, status: "running" },
    data: { stopRequested: true },
  });
  return running.count > 0;
}

export type RunDetail = NonNullable<Awaited<ReturnType<typeof getRun>>>;
export type RunRow = Awaited<ReturnType<typeof listRuns>>[number];
