/**
 * Critical flows per target (run 7, M4; roadmap item 2): the journeys a team wants covered on
 * every run, in plain language. The worker completes each one with the agent once, saves the
 * steps as a replayable script, and replays it without a model on later runs. Editing a
 * journey's wording drops its script, so the agent learns it again. Tenant client throughout.
 */
import { Prisma } from "@/lib/generated/prisma/client";
import { inTenant, tenantDb, workspaceOf, type TenantContext } from "@/lib/tenant-db";

export const MAX_FLOWS = 10; // also enforced by the database (flows_per_target_limit)

type Errors = Partial<Record<"name" | "goal", string>>;
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

export function parseFlowInput(body: Record<string, unknown>): { ok: true; value: { name: string; goal: string } } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const name = text(body.name);
  const goal = text(body.goal);
  if (!name) errors.name = "Name the journey, e.g. Checkout.";
  else if (name.length > 100) errors.name = "At most 100 characters.";
  if (!goal) errors.goal = "Describe the journey as a user would do it.";
  else if (goal.length > 2000) errors.goal = "At most 2,000 characters.";
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, value: { name, goal } };
}

export type FlowView = {
  id: string;
  name: string;
  goal: string;
  /** How many steps the saved script replays; null until the agent has completed it once. */
  scriptSteps: number | null;
  lastStatus: string | null;
  lastRunId: string | null;
};

type FlowRow = { id: string; name: string; goal: string; script: unknown; lastStatus: string | null; lastRunId: string | null };

function toView(row: FlowRow): FlowView {
  const steps = (row.script as { steps?: unknown[] } | null)?.steps;
  return { id: row.id, name: row.name, goal: row.goal, scriptSteps: Array.isArray(steps) ? steps.length : null, lastStatus: row.lastStatus, lastRunId: row.lastRunId };
}

export async function listFlows(scope: string | TenantContext, targetId: string): Promise<FlowView[]> {
  if (!isUuid(targetId)) return [];
  const rows = await tenantDb(scope).flow.findMany({ where: { targetId, workspaceId: workspaceOf(scope) }, orderBy: [{ position: "asc" }, { createdAt: "asc" }] });
  return rows.map(toView);
}

export async function createFlow(scope: string | TenantContext, targetId: string, body: Record<string, unknown>) {
  const parsed = parseFlowInput(body);
  if (!parsed.ok) return parsed;
  if (!isUuid(targetId)) return { ok: false as const, notFound: true as const, errors: {} };
  const workspaceId = workspaceOf(scope);
  return inTenant(scope, async (tx) => {
    const target = await tx.target.findFirst({ where: { id: targetId, workspaceId } });
    if (!target) return { ok: false as const, notFound: true as const, errors: {} };
    const count = await tx.flow.count({ where: { targetId } });
    if (count >= MAX_FLOWS) return { ok: false as const, errors: { name: `A target has at most ${MAX_FLOWS} critical flows.` } as Errors };
    const row = await tx.flow.create({ data: { workspaceId, targetId, position: count, ...parsed.value } });
    return { ok: true as const, flow: toView(row) };
  });
}

export async function updateFlow(scope: string | TenantContext, id: string, body: Record<string, unknown>) {
  const parsed = parseFlowInput(body);
  if (!parsed.ok) return parsed;
  if (!isUuid(id)) return { ok: false as const, notFound: true as const, errors: {} };
  const workspaceId = workspaceOf(scope);
  const row = await inTenant(scope, async (tx) => {
    const flow = await tx.flow.findFirst({ where: { id, workspaceId } });
    if (!flow) return null;
    // A new wording is a new journey: the old script may not match it, so the agent learns it again.
    const relearn = flow.goal !== parsed.value.goal;
    return tx.flow.update({
      where: { id },
      data: { ...parsed.value, ...(relearn ? { script: Prisma.DbNull, scriptSavedAt: null, lastStatus: null } : {}) },
    });
  });
  if (!row) return { ok: false as const, notFound: true as const, errors: {} };
  return { ok: true as const, flow: toView(row) };
}

export async function deleteFlow(scope: string | TenantContext, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const { count } = await tenantDb(scope).flow.deleteMany({ where: { id, workspaceId: workspaceOf(scope) } });
  return count > 0;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
