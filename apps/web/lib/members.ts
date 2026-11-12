/**
 * Members, roles and invitation links (run 4, J5).
 *
 * A user belongs to one workspace. An admin creates an invitation link for a role (never owner:
 * ownership is transferred, not handed out); the link's token is shown once and stored as a
 * SHA-256 hash; it expires (7 days by default) and can be revoked. Accepting moves the user into
 * the workspace with that role. No email is sent: the admin copies the link.
 * Every change is written to the audit log by the database (triggers on users and invitations).
 */
import { createHash, randomBytes } from "node:crypto";
import { acceptInvitationByHash, invitationByHash, userMessage } from "@/lib/system-db";
import { inTenant, tenantDb } from "@/lib/tenant-db";
import { can, canAssign, type Role } from "@/lib/roles";

export const INVITE_DAYS = 7;
type Actor = { id: string; role: Role };
type Result<T = object> = ({ ok: true } & T) | { ok: false; error: string; status?: number };

const hashToken = (token: string) => createHash("sha256").update(token, "utf8").digest("hex");

export type MemberView = { id: string; email: string; name: string | null; role: Role; joinedAt: string };
export type InvitationView = { id: string; role: Role; expiresAt: string; createdAt: string };

export async function listMembers(workspaceId: string): Promise<MemberView[]> {
  const users = await tenantDb(workspaceId).user.findMany({ where: { workspaceId }, orderBy: { createdAt: "asc" } });
  return users.map((u) => ({ id: u.id, email: u.email, name: u.name, role: u.role, joinedAt: u.createdAt.toISOString() }));
}

export async function listInvitations(workspaceId: string): Promise<InvitationView[]> {
  const rows = await tenantDb(workspaceId).invitation.findMany({
    where: { workspaceId, acceptedAt: null, revokedAt: null, expiresAt: { gt: new Date() } },
    orderBy: { createdAt: "desc" },
  });
  return rows.map((r) => ({ id: r.id, role: r.role, expiresAt: r.expiresAt.toISOString(), createdAt: r.createdAt.toISOString() }));
}

/** Returns the link's token once. `days` < 0 only in tests (an already expired link). */
export async function createInvitation(workspaceId: string, actor: Actor, role: Role, days = INVITE_DAYS): Promise<Result<{ token: string; invitation: InvitationView }>> {
  if (!can(actor.role, "members.manage")) return { ok: false, error: "Only owners and admins can invite people." };
  if (role === "owner") return { ok: false, error: "Ownership can't be given by a link: invite them, then transfer ownership." };
  const token = "inv_" + randomBytes(24).toString("base64url");
  const expiresAt = new Date(Date.now() + days * 86_400_000);
  // An invitation expires after it is created (a database check); a test's already-expired
  // link is dated back accordingly.
  const createdAt = new Date(Math.min(Date.now(), expiresAt.getTime() - 60_000));
  const row = await tenantDb({ workspaceId, userId: actor.id }).invitation.create({
    data: { workspaceId, tokenHash: hashToken(token), role, createdById: actor.id, expiresAt, createdAt },
  });
  return { ok: true, token, invitation: { id: row.id, role: row.role, expiresAt: row.expiresAt.toISOString(), createdAt: row.createdAt.toISOString() } };
}

export async function revokeInvitation(workspaceId: string, id: string, userId: string | null = null): Promise<boolean> {
  return (await tenantDb({ workspaceId, userId }).invitation.updateMany({ where: { id, workspaceId, acceptedAt: null, revokedAt: null }, data: { revokedAt: new Date() } })).count > 0;
}

/** What the invitation page shows before accepting (null: not valid). */
export async function invitationPreview(token: string) {
  const invite = await invitationByHash(hashToken(token));
  if (!invite || invite.acceptedAt || invite.revokedAt || invite.expiresAt <= new Date()) return null;
  return { workspaceName: invite.workspaceName, role: invite.role, expiresAt: invite.expiresAt.toISOString() };
}

/**
 * Accepting moves the user from their own workspace into the inviting one: a database function
 * (accept_invitation) checks the link, the ownership rule and the move in one transaction, and a
 * link works once even if two people open it at the same moment (it locks the invitation).
 */
export async function acceptInvitation(token: string, userId: string): Promise<Result<{ workspaceId: string }>> {
  return acceptInvitationByHash(hashToken(token), userId);
}

export async function changeRole(workspaceId: string, actor: Actor, targetId: string, role: Role): Promise<Result> {
  const members = tenantDb({ workspaceId, userId: actor.id });
  const target = await members.user.findFirst({ where: { id: targetId, workspaceId } });
  if (!target) return { ok: false, error: "Member not found.", status: 404 };
  if (!canAssign(actor.role, target.role, role)) return { ok: false, error: "Your role can't make this change." };
  await members.user.update({ where: { id: targetId }, data: { role } });
  return { ok: true };
}

/** The removed person keeps their account, in a new workspace of their own. */
export async function removeMember(workspaceId: string, actor: Actor, targetId: string): Promise<Result> {
  if (!can(actor.role, "members.manage")) return { ok: false, error: "Only owners and admins can remove members." };
  try {
    // A database function: the member leaves this workspace for a new one of their own, which
    // no single workspace's rows can express (remove_member, run 5).
    await inTenant({ workspaceId, userId: actor.id }, (tx) => tx.$queryRaw`SELECT remove_member(${targetId}::uuid)`);
  } catch (error) {
    const message = userMessage(error);
    if (!message) throw error;
    return { ok: false, error: message, status: message === "Member not found." ? 404 : undefined };
  }
  return { ok: true };
}

export async function transferOwnership(workspaceId: string, actor: Actor, targetId: string): Promise<Result> {
  if (!can(actor.role, "workspace.transfer") || actor.id === targetId) return { ok: false, error: "Only the owner can hand over ownership, to someone else." };
  const done = await inTenant({ workspaceId, userId: actor.id }, async (tx) => {
    const target = await tx.user.findFirst({ where: { id: targetId, workspaceId } });
    if (!target) return false;
    await tx.user.update({ where: { id: actor.id }, data: { role: "admin" } });
    await tx.user.update({ where: { id: targetId }, data: { role: "owner" } });
    return true;
  });
  if (!done) return { ok: false, error: "Member not found.", status: 404 };
  return { ok: true };
}
