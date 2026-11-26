/**
 * Deep mode in the web app (run 9): a workspace's own limits, and resuming a paused run.
 *
 * Deep runs default to 400 steps and 60 minutes (the worker's DEEP_MAX_STEPS / DEEP_MAX_SECONDS).
 * A workspace's owners and admins may set their own, higher or lower; a run (an API caller) can
 * only lower them. Empty = the product default.
 */
import { inTenant, tenantDb } from "@/lib/tenant-db";
import { isUuid } from "@/lib/runs";

export const DEFAULT_DEEP_STEPS = 400;
export const DEFAULT_DEEP_MINUTES = 60;
export const MAX_DEEP_STEPS = 5000;
export const MAX_DEEP_MINUTES = 600;

export type DeepLimitsInput = { steps: number | null; minutes: number | null };
export type DeepLimitsResult = { ok: true; value: DeepLimitsInput } | { ok: false; errors: Partial<Record<"steps" | "minutes", string>> };

function limit(value: unknown, max: number): number | null | undefined {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isInteger(n) && n >= 1 && n <= max ? n : undefined;
}

/** Validate the settings form: whole numbers in range, or empty for the default. */
export function parseDeepLimits(body: { steps?: unknown; minutes?: unknown }): DeepLimitsResult {
  const steps = limit(body.steps, MAX_DEEP_STEPS);
  const minutes = limit(body.minutes, MAX_DEEP_MINUTES);
  const errors: Partial<Record<"steps" | "minutes", string>> = {};
  if (steps === undefined) errors.steps = `A whole number from 1 to ${MAX_DEEP_STEPS}, or empty for ${DEFAULT_DEEP_STEPS}.`;
  if (minutes === undefined) errors.minutes = `A whole number from 1 to ${MAX_DEEP_MINUTES}, or empty for ${DEFAULT_DEEP_MINUTES}.`;
  if (steps === undefined || minutes === undefined) return { ok: false, errors };
  return { ok: true, value: { steps, minutes } };
}

export async function saveDeepLimits(workspaceId: string, userId: string | null, limits: DeepLimitsInput) {
  await inTenant({ workspaceId, userId }, (tx) =>
    tx.workspace.update({
      where: { id: workspaceId },
      data: { deepMaxSteps: limits.steps, deepMaxSeconds: limits.minutes === null ? null : limits.minutes * 60 },
    }),
  );
}

export async function deepLimits(workspaceId: string): Promise<DeepLimitsInput> {
  const ws = await tenantDb(workspaceId).workspace.findUniqueOrThrow({
    where: { id: workspaceId },
    select: { deepMaxSteps: true, deepMaxSeconds: true },
  });
  return { steps: ws.deepMaxSteps, minutes: ws.deepMaxSeconds === null ? null : Math.round(ws.deepMaxSeconds / 60) };
}

/** Queue a paused deep run again; the worker continues it from its saved coverage. */
export async function requestResume(workspaceId: string, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const resumed = await tenantDb(workspaceId).run.updateMany({
    where: { id, workspaceId, status: "paused" },
    data: { status: "queued", pausedReason: null },
  });
  return resumed.count > 0;
}
