/**
 * Usage you could bill for (run 5, K4). The database records one usage event per finished run
 * (trigger runs_record_usage), with the explorer's and the reviewer's tokens and cost apart, and
 * enforces each workspace's plan (consume_quota). This module only reads them.
 */
import { startOfMonth } from "@/lib/limits";
import { platformUsageRows } from "@/lib/system-db";
import { inTenant } from "@/lib/tenant-db";

export type PlanView = {
  id: string;
  name: string;
  runsPerMonth: number;
  maxStepsPerRun: number;
  /** Empty: every provider. */
  allowedProviders: string[];
  seats: number;
  retentionDays: number;
  priceUsdMonth: number | null;
};

export type ModelUsage = { role: "explorer" | "reviewer"; provider: string; model: string; runs: number; inputTokens: number; outputTokens: number; costUsd: number };

export type WorkspaceUsage = {
  plan: PlanView;
  /** The monthly limit that applies: the lower of the plan's and the workspace's own quota. */
  quota: number;
  since: string;
  runs: number;
  costUsd: number;
  seatsUsed: number;
  retentionDays: number;
  byModel: ModelUsage[];
};

export async function workspaceUsage(workspaceId: string, now = new Date()): Promise<WorkspaceUsage> {
  const since = startOfMonth(now);
  return inTenant(workspaceId, async (tx) => {
    const workspace = await tx.workspace.findUniqueOrThrow({ where: { id: workspaceId }, include: { plan: true } });
    const runs = await tx.run.count({ where: { workspaceId, createdAt: { gte: since } } });
    const seatsUsed = await tx.user.count({ where: { workspaceId } });
    const rows = await tx.$queryRaw<{ role: "explorer" | "reviewer"; provider: string; model: string; runs: bigint; input: bigint; output: bigint; cost: number }[]>`
      SELECT 'explorer' AS role, explorer_provider AS provider, explorer_model AS model, count(*) AS runs,
             sum(explorer_input_tokens) AS input, sum(explorer_output_tokens) AS output, sum(explorer_cost_usd) AS cost
        FROM usage_events WHERE workspace_id = ${workspaceId}::uuid AND created_at >= ${since} AND explorer_model IS NOT NULL
       GROUP BY 2, 3
      UNION ALL
      SELECT 'reviewer', reviewer_provider, reviewer_model, count(*),
             sum(reviewer_input_tokens), sum(reviewer_output_tokens), sum(reviewer_cost_usd)
        FROM usage_events WHERE workspace_id = ${workspaceId}::uuid AND created_at >= ${since} AND reviewer_model IS NOT NULL
       GROUP BY 2, 3
      ORDER BY 1, 2, 3`;
    const byModel = rows.map((r) => ({ role: r.role, provider: r.provider, model: r.model, runs: Number(r.runs), inputTokens: Number(r.input), outputTokens: Number(r.output), costUsd: Number(r.cost) }));
    const { plan } = workspace;
    return {
      plan: { id: plan.id, name: plan.name, runsPerMonth: plan.runsPerMonth, maxStepsPerRun: plan.maxStepsPerRun, allowedProviders: plan.allowedProviders, seats: plan.seats, retentionDays: plan.retentionDays, priceUsdMonth: plan.priceUsdMonth },
      quota: Math.min(plan.runsPerMonth, workspace.monthlyRunQuota),
      since: since.toISOString(),
      runs,
      costUsd: byModel.reduce((sum, m) => sum + m.costUsd, 0),
      seatsUsed,
      retentionDays: Math.min(plan.retentionDays, workspace.retentionDays),
      byModel,
    };
  });
}

export type PlatformRow = { workspaceId: string; name: string; slug: string; planId: string; members: number; runs: number; explorerCostUsd: number; reviewerCostUsd: number; inputTokens: number; outputTokens: number };

/** Usage across every workspace this month, for a platform admin; null for anyone else. */
export async function platformUsage(userId: string, now = new Date()): Promise<PlatformRow[] | null> {
  return platformUsageRows(userId, startOfMonth(now));
}
