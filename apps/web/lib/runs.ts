/**
 * Reading and writing runs. The web app's only link to the worker is these rows: it inserts a
 * "queued" run, the worker claims it and writes steps, bugs, cost and status back.
 *
 * Every function takes the workspaceId and filters by it, so one workspace can never read or
 * change another's runs.
 */
import { db } from "@/lib/db";
import type { RunInput } from "@/lib/targets";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID.test(value);
}

export async function createRun(workspaceId: string, userId: string | null, input: RunInput) {
  const run = await db.run.create({
    data: {
      workspaceId,
      createdById: userId,
      targetUrl: input.targetUrl,
      mode: input.mode,
      focus: input.focus,
    },
  });
  await db.auditLog.create({
    data: {
      workspaceId,
      userId,
      action: "run.started",
      targetUrl: input.targetUrl,
      mode: input.mode,
      runId: run.id,
    },
  });
  return run;
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
