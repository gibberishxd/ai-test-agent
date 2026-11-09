/** Data for the settings page: domains, usage and the audit log, always scoped to a workspace. */
import { db } from "@/lib/db";
import { normalizeHostname, realDeps, verifyDomain, type VerifyDeps } from "@/lib/domains";
import { startOfMonth } from "@/lib/limits";

export async function listDomains(workspaceId: string) {
  return db.domain.findMany({ where: { workspaceId }, orderBy: { createdAt: "asc" } });
}

export async function addDomain(workspaceId: string, input: string) {
  const hostname = normalizeHostname(input);
  if (!hostname) return { ok: false as const, error: "Enter a domain like shop.example.com." };
  const domain = await db.domain.upsert({
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
  const domain = await db.domain.findFirst({ where: { id: domainId, workspaceId } });
  if (!domain) return { ok: false as const, reason: "Domain not found." };
  const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
  const result = await verifyDomain(domain.hostname, workspace.verificationToken, deps);
  if (!result.ok) return result;
  await db.domain.update({ where: { id: domain.id }, data: { verifiedAt: new Date(), method: result.method } });
  await db.auditLog.create({
    data: { workspaceId, userId, action: "domain.verified", targetUrl: `https://${domain.hostname}`, metadata: { method: result.method } },
  });
  return result;
}

export async function usageThisMonth(workspaceId: string) {
  const since = startOfMonth(new Date());
  const [workspace, runs, byProvider] = await Promise.all([
    db.workspace.findUniqueOrThrow({ where: { id: workspaceId } }),
    db.run.aggregate({ where: { workspaceId, createdAt: { gte: since } }, _count: true, _sum: { costUsd: true } }),
    db.run.groupBy({
      by: ["provider"],
      where: { workspaceId, createdAt: { gte: since } },
      _count: true,
      _sum: { costUsd: true },
    }),
  ]);
  return {
    quota: workspace.monthlyRunQuota,
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
  return db.auditLog.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "desc" },
    take,
    include: { user: { select: { email: true } } },
  });
}
