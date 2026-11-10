/**
 * Read-only share links for a run's report. The link is /share/<token>: 24 random bytes
 * (192 bits) are unguessable, and revoking sets the token to null, so the old link stops
 * working immediately.
 */
import { randomBytes } from "node:crypto";
import { db } from "@/lib/db";
import { isUuid } from "@/lib/runs";

const SHARE_TOKEN = /^[A-Za-z0-9_-]{32}$/;

export function newShareToken(): string {
  return randomBytes(24).toString("base64url");
}

export async function createShareLink(workspaceId: string, runId: string): Promise<string | null> {
  if (!isUuid(runId)) return null;
  const run = await db.run.findFirst({ where: { id: runId, workspaceId } });
  if (!run) return null;
  if (run.shareToken) return run.shareToken;
  const token = newShareToken();
  await db.run.update({ where: { id: run.id }, data: { shareToken: token } });
  return token;
}

export async function revokeShareLink(workspaceId: string, runId: string): Promise<boolean> {
  if (!isUuid(runId)) return false;
  const result = await db.run.updateMany({ where: { id: runId, workspaceId }, data: { shareToken: null } });
  return result.count > 0;
}

/** The shared run for a token, or null (unknown or revoked). Needs no sign-in. */
export async function getSharedRun(token: string) {
  if (!SHARE_TOKEN.test(token)) return null;
  return db.run.findFirst({
    where: { shareToken: token },
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
  const byToken = access.shareToken && SHARE_TOKEN.test(access.shareToken);
  const run = await db.run.findFirst({
    where: byToken
      ? { id: runId, shareToken: access.shareToken }
      : { id: runId, workspaceId: access.workspaceId },
    select: { id: true },
  });
  return run !== null;
}
