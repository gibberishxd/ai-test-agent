/** Data for the settings page: domains, usage and the audit log, always scoped to a workspace. */
import { tenantDb } from "@/lib/tenant-db";
import { normalizeHostname, realDeps, verifyDomain, type VerifyDeps } from "@/lib/domains";
import { startOfMonth } from "@/lib/limits";

export async function listDomains(workspaceId: string) {
  return tenantDb(workspaceId).domain.findMany({ where: { workspaceId }, orderBy: { createdAt: "asc" } });
}

export async function addDomain(workspaceId: string, input: string) {
  const hostname = normalizeHostname(input);
  if (!hostname) return { ok: false as const, error: "Enter a domain like shop.example.com." };
  const domain = await tenantDb(workspaceId).domain.upsert({
    where: { workspaceId_hostname: { workspaceId, hostname } },
    update: {},
    create: { workspaceId, hostname },
  });
  return { ok: true as const, domain };
}

export async function checkDomain(
  workspaceId: string,
  userId: string | null,
  domainId: string,
  deps: VerifyDeps = realDeps,
) {
  const domain = await tenantDb(workspaceId).domain.findFirst({ where: { id: domainId, workspaceId } });
  if (!domain) return { ok: false as const, reason: "Domain not found." };
  const workspace = await tenantDb(workspaceId).workspace.findUniqueOrThrow({ where: { id: workspaceId } });
  const result = await verifyDomain(domain.hostname, workspace.verificationToken, deps);
  if (!result.ok) return result;
  // The database logs "domain.verified" (trigger domains_audit) with this user as the actor.
  await tenantDb({ workspaceId, userId }).domain.update({ where: { id: domain.id }, data: { verifiedAt: new Date(), method: result.method } });
  return result;
}

export async function usageThisMonth(workspaceId: string) {
  const since = startOfMonth(new Date());
  const [workspace, runs, byProvider] = await Promise.all([
    tenantDb(workspaceId).workspace.findUniqueOrThrow({ where: { id: workspaceId }, include: { plan: true } }),
    tenantDb(workspaceId).run.aggregate({ where: { workspaceId, createdAt: { gte: since } }, _count: true, _sum: { costUsd: true } }),
    tenantDb(workspaceId).run.groupBy({
      by: ["provider"],
      where: { workspaceId, createdAt: { gte: since } },
      _count: true,
      _sum: { costUsd: true },
    }),
  ]);
  return {
    // The limit that applies: the lower of the plan's and the workspace's own (consume_quota).
    quota: Math.min(workspace.monthlyRunQuota, workspace.plan.runsPerMonth),
    runs: runs._count,
    costUsd: runs._sum.costUsd ?? 0,
    byProvider: byProvider.map((row) => ({
      provider: row.provider ?? "not started",
      runs: row._count,
      costUsd: row._sum.costUsd ?? 0,
    })),
  };
}

export async function auditLog(workspaceId: string, take = 50) {
  return tenantDb(workspaceId).auditLog.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "desc" },
    take,
    include: { user: { select: { email: true } } },
  });
}
