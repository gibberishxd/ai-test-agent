/**
 * Members, roles and invitation links (run 4, J5).
 *
 * A user belongs to one workspace. An admin creates an invitation link for a role (never owner:
 * ownership is transferred, not handed out); the link's token is shown once and stored as a
 * SHA-256 hash; it expires (7 days by default) and can be revoked. Accepting moves the user into
 * the workspace with that role. No email is sent: the admin copies the link.
 * Every change is written to the audit log.
 */
import { createHash, randomBytes } from "node:crypto";
import { db } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
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
  const rows = await db.invitation.findMany({
    where: { workspaceId, acceptedAt: null, revokedAt: null, expiresAt: { gt: new Date() } },
    orderBy: { createdAt: "desc" },
  });
  return rows.map((r) => ({ id: r.id, role: r.role, expiresAt: r.expiresAt.toISOString(), createdAt: r.createdAt.toISOString() }));
}

async function audit(workspaceId: string, userId: string | null, action: string, metadata: Record<string, string>) {
  await db.auditLog.create({ data: { workspaceId, userId, action, metadata } });
}

/** Returns the link's token once. `days` < 0 only in tests (an already expired link). */
export async function createInvitation(workspaceId: string, actor: Actor, role: Role, days = INVITE_DAYS): Promise<Result<{ token: string; invitation: InvitationView }>> {
  if (!can(actor.role, "members.manage")) return { ok: false, error: "Only owners and admins can invite people." };
  if (role === "owner") return { ok: false, error: "Ownership can't be given by a link: invite them, then transfer ownership." };
  const token = "inv_" + randomBytes(24).toString("base64url");
  const row = await db.invitation.create({
    data: { workspaceId, tokenHash: hashToken(token), role, createdById: actor.id, expiresAt: new Date(Date.now() + days * 86_400_000) },
  });
  await audit(workspaceId, actor.id, "member.invited", { role });
  return { ok: true, token, invitation: { id: row.id, role: row.role, expiresAt: row.expiresAt.toISOString(), createdAt: row.createdAt.toISOString() } };
}

export async function revokeInvitation(workspaceId: string, id: string): Promise<boolean> {
  return (await db.invitation.updateMany({ where: { id, workspaceId, acceptedAt: null, revokedAt: null }, data: { revokedAt: new Date() } })).count > 0;
}

/** What the invitation page shows before accepting (null: not valid). */
export async function invitationPreview(token: string) {
  const invite = await db.invitation.findUnique({ where: { tokenHash: hashToken(token) }, include: { workspace: true } });
  if (!invite || invite.acceptedAt || invite.revokedAt || invite.expiresAt <= new Date()) return null;
  return { workspaceName: invite.workspace.name, role: invite.role, expiresAt: invite.expiresAt.toISOString() };
}

export async function acceptInvitation(token: string, userId: string): Promise<Result<{ workspaceId: string }>> {
  return db.$transaction(async (tx) => {
    const invite = await tx.invitation.findUnique({ where: { tokenHash: hashToken(token) } });
    if (!invite || invite.acceptedAt || invite.revokedAt || invite.expiresAt <= new Date()) {
      return { ok: false as const, error: "This invitation link is no longer valid. Ask for a new one." };
    }
    const user = await tx.user.findUniqueOrThrow({ where: { id: userId } });
    if (user.role === "owner" && user.workspaceId !== invite.workspaceId) {
      const others = await tx.user.count({ where: { workspaceId: user.workspaceId, NOT: { id: userId } } });
      if (others > 0) return { ok: false as const, error: "You own a workspace with other members: transfer ownership first." };
    }
    // A link works once, even if two people open it at the same moment.
    const claimed = await tx.invitation.updateMany({ where: { id: invite.id, acceptedAt: null }, data: { acceptedAt: new Date(), acceptedById: userId } });
    if (claimed.count === 0) return { ok: false as const, error: "This invitation link was just used." };
    await tx.user.update({ where: { id: userId }, data: { workspaceId: invite.workspaceId, role: invite.role } });
    await tx.auditLog.create({ data: { workspaceId: invite.workspaceId, userId, action: "member.joined", metadata: { role: invite.role } } });
    return { ok: true as const, workspaceId: invite.workspaceId };
  });
}

export async function changeRole(workspaceId: string, actor: Actor, targetId: string, role: Role): Promise<Result> {
  const target = await db.user.findFirst({ where: { id: targetId, workspaceId } });
  if (!target) return { ok: false, error: "Member not found.", status: 404 };
  if (!canAssign(actor.role, target.role, role)) return { ok: false, error: "Your role can't make this change." };
  await db.user.update({ where: { id: targetId }, data: { role } });
  await audit(workspaceId, actor.id, "member.role_changed", { member: target.email, from: target.role, to: role });
  return { ok: true };
}

/** The removed person keeps their account, in a new workspace of their own. */
export async function removeMember(workspaceId: string, actor: Actor, targetId: string): Promise<Result> {
  if (!can(actor.role, "members.manage")) return { ok: false, error: "Only owners and admins can remove members." };
  const target = await db.user.findFirst({ where: { id: targetId, workspaceId } });
  if (!target) return { ok: false, error: "Member not found.", status: 404 };
  if (target.role === "owner") return { ok: false, error: "The owner can't be removed: transfer ownership first." };
  await db.$transaction(async (tx) => {
    const own = await tx.workspace.create({
      data: { name: `${target.name || target.email.split("@")[0]}'s workspace`, slug: `${target.email.split("@")[0].toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${randomBytes(2).toString("hex")}` },
    });
    await tx.user.update({ where: { id: targetId }, data: { workspaceId: own.id, role: "owner" } });
  });
  await audit(workspaceId, actor.id, "member.removed", { member: target.email });
  return { ok: true };
}

export async function transferOwnership(workspaceId: string, actor: Actor, targetId: string): Promise<Result> {
  if (!can(actor.role, "workspace.transfer") || actor.id === targetId) return { ok: false, error: "Only the owner can hand over ownership, to someone else." };
  const target = await db.user.findFirst({ where: { id: targetId, workspaceId } });
  if (!target) return { ok: false, error: "Member not found.", status: 404 };
  await db.$transaction([
    db.user.update({ where: { id: actor.id }, data: { role: "admin" } }),
    db.user.update({ where: { id: targetId }, data: { role: "owner" } }),
  ]);
  await audit(workspaceId, actor.id, "member.ownership_transferred", { to: target.email });
  return { ok: true };
}
