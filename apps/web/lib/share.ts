import { sharedRunRef } from "@/lib/system-db";
/**
 * Read-only share links for a run's report. The link is /share/<token>: 24 random bytes
 * (192 bits) are unguessable, and revoking sets the token to null, so the old link stops
 * working immediately.
 */
import { randomBytes } from "node:crypto";
import { db } from "@/lib/db";
import { inTenant, tenantDb, workspaceOf, type TenantContext } from "@/lib/tenant-db";
import { isUuid } from "@/lib/runs";

const SHARE_TOKEN = /^[A-Za-z0-9_-]{32}$/;

export function newShareToken(): string {
  return randomBytes(24).toString("base64url");
}

export async function createShareLink(scope: string | TenantContext, runId: string): Promise<string | null> {
  const workspaceId = workspaceOf(scope);
  if (!isUuid(runId)) return null;
  const run = await tenantDb(scope).run.findFirst({ where: { id: runId, workspaceId } });
  if (!run) return null;
  if (run.shareToken) return run.shareToken;
  const token = newShareToken();
  await tenantDb(scope).run.update({ where: { id: run.id }, data: { shareToken: token } });
  return token;
}

export async function revokeShareLink(scope: string | TenantContext, runId: string): Promise<boolean> {
  const workspaceId = workspaceOf(scope);
  if (!isUuid(runId)) return false;
  const result = await tenantDb(scope).run.updateMany({ where: { id: runId, workspaceId }, data: { shareToken: null } });
  return result.count > 0;
}

/** The shared run for a token, or null (unknown or revoked). Needs no sign-in. */
export async function getSharedRun(token: string) {
  if (!SHARE_TOKEN.test(token)) return null;
  // The token is the credential: a database function finds the run's workspace.
  const ref = await sharedRunRef(token);
  if (!ref) return null;
  return tenantDb(ref.workspaceId).run.findFirst({
    where: { id: ref.id, shareToken: token },
    include: { steps: { orderBy: { index: "asc" } }, bugs: { orderBy: { createdAt: "asc" } } },
  });
}

/**
 * May this request read a stored file (key "<run id>/<name>")? Yes if the run belongs to the
 * caller's workspace, or if the caller holds the share token of that same run. A token never
 * opens another run's files, and a revoked token opens nothing.
 */
export async function canReadFile(
  key: string,
  access: { workspaceId: string; shareToken: string | null },
): Promise<boolean> {
  const runId = key.split("/")[0] ?? "";
  if (!isUuid(runId)) return false;
  if (access.shareToken && SHARE_TOKEN.test(access.shareToken)) {
    const ref = await sharedRunRef(access.shareToken);
    return ref?.id === runId;
  }
  const run = await tenantDb(access.workspaceId).run.findFirst({
    where: { id: runId, workspaceId: access.workspaceId },
    select: { id: true },
  });
  return run !== null;
}
