/**
 * What the web app does outside one workspace (run 5, K3), each through a narrow database
 * function owned by the schema owner: the app role itself can't read across workspaces.
 * docs/DATABASE.md, "Justified bypasses", says why each one exists.
 */
import { db } from "@/lib/db";
import type { Role } from "@/lib/roles";

/** The shared demo workspace visitors use (created on first use). */
export async function demoWorkspaceId(): Promise<string> {
  const [row] = await db.$queryRaw<{ id: string }[]>`SELECT demo_workspace() AS id`;
  return row.id;
}

export type KeyRow = { id: string; workspaceId: string; createdById: string | null; revokedAt: Date | null };

/** The API key with this hash, if any: the hash is the credential. */
export async function apiKeyByHash(hash: string): Promise<KeyRow | null> {
  const rows = await db.$queryRaw<{ id: string; workspace_id: string; created_by_id: string | null; revoked_at: Date | null }[]>`
    SELECT * FROM api_key_by_hash(${hash})`;
  const row = rows[0];
  return row ? { id: row.id, workspaceId: row.workspace_id, createdById: row.created_by_id, revokedAt: row.revoked_at } : null;
}

/** The run a public share token points at (id and workspace), if any. */
export async function sharedRunRef(token: string): Promise<{ id: string; workspaceId: string } | null> {
  const rows = await db.$queryRaw<{ id: string; workspace_id: string }[]>`SELECT * FROM shared_run(${token})`;
  return rows[0] ? { id: rows[0].id, workspaceId: rows[0].workspace_id } : null;
}

export type InvitationRow = {
  id: string;
  workspaceId: string;
  workspaceName: string;
  role: Role;
  expiresAt: Date;
  acceptedAt: Date | null;
  revokedAt: Date | null;
};

export async function invitationByHash(hash: string): Promise<InvitationRow | null> {
  const rows = await db.$queryRaw<
    { id: string; workspace_id: string; workspace_name: string; role: Role; expires_at: Date; accepted_at: Date | null; revoked_at: Date | null }[]
  >`SELECT * FROM invitation_by_token(${hash})`;
  const row = rows[0];
  return row
    ? { id: row.id, workspaceId: row.workspace_id, workspaceName: row.workspace_name, role: row.role, expiresAt: row.expires_at, acceptedAt: row.accepted_at, revokedAt: row.revoked_at }
    : null;
}

/**
 * The message of an error the database raised for the user (RAISE ... ERRCODE P0001/P0002 in
 * our functions), or null for any other error. Prisma reports a failed raw query as
 * "Raw query failed. Code: `P0001`. Message: `<text>`".
 */
export function userMessage(error: unknown): string | null {
  const text = error instanceof Error ? error.message : String(error);
  const match = /Code: `P000[12]`\. Message: `([^`]*)`/.exec(text);
  return match ? match[1] : null;
}

export async function acceptInvitationByHash(hash: string, userId: string): Promise<{ ok: true; workspaceId: string } | { ok: false; error: string }> {
  try {
    const rows = await db.$queryRaw<{ workspace_id: string }[]>`SELECT * FROM accept_invitation(${hash}, ${userId}::uuid)`;
    return { ok: true, workspaceId: rows[0].workspace_id };
  } catch (error) {
    const message = userMessage(error);
    if (message) return { ok: false, error: message };
    throw error;
  }
}

export type MetricRow = { metric: string; label: string; value: number };

/** Totals across all workspaces for /api/metrics: counts and sums, never tenant rows. */
export async function serviceMetrics(): Promise<MetricRow[]> {
  return db.$queryRaw<MetricRow[]>`SELECT * FROM service_metrics()`;
}

/**
 * Usage across every workspace, for a platform admin (users.is_platform_admin, set from the CLI).
 * The database checks the flag (platform_usage); anyone else gets null.
 */
export async function platformUsageRows(userId: string, since: Date) {
  try {
    const [, rows] = await db.$transaction([
      db.$executeRaw`SELECT set_config('app.user_id', ${userId}, true)`,
      db.$queryRaw<
        { workspace_id: string; name: string; slug: string; plan_id: string; members: number; runs: number; explorer_cost_usd: number; reviewer_cost_usd: number; input_tokens: bigint; output_tokens: bigint }[]
      >`SELECT * FROM platform_usage(${since})`,
    ]);
    return rows.map((r) => ({
      workspaceId: r.workspace_id,
      name: r.name,
      slug: r.slug,
      planId: r.plan_id,
      members: Number(r.members),
      runs: Number(r.runs),
      explorerCostUsd: Number(r.explorer_cost_usd),
      reviewerCostUsd: Number(r.reviewer_cost_usd),
      inputTokens: Number(r.input_tokens),
      outputTokens: Number(r.output_tokens),
    }));
  } catch (error) {
    if (userMessage(error)) return null;
    throw error;
  }
}
