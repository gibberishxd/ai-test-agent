/** Run 4, J5: members, roles and invitation links against a real Postgres. */
import { beforeEach, describe, expect, it } from "vitest";
import { createUserWithWorkspace } from "@/lib/auth-adapter";
import { db } from "@/lib/db";
import {
  acceptInvitation,
  changeRole,
  createInvitation,
  listMembers,
  removeMember,
  revokeInvitation,
  transferOwnership,
} from "@/lib/members";
import { hasTestDb } from "../test/use-test-db";

async function user(email: string) {
  const created = await createUserWithWorkspace(db, { email });
  return db.user.findUniqueOrThrow({ where: { id: created.id } });
}

describe.skipIf(!hasTestDb)("members and invitations (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, users, invitations, audit_log CASCADE");
  });

  it("the person who signs up owns their workspace", async () => {
    expect((await user("ana@example.com")).role).toBe("owner");
  });

  it("an invitation link adds someone with its role, once", async () => {
    const owner = await user("ana@example.com");
    const guest = await user("ben@example.com");
    const invite = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "member");
    if (!invite.ok) throw new Error(invite.error);
    expect(invite.token).toMatch(/^inv_/);
    expect(await db.invitation.findFirst({ where: { tokenHash: invite.token } })).toBeNull(); // only the hash is stored

    expect(await acceptInvitation(invite.token, guest.id)).toMatchObject({ ok: true });
    const joined = await db.user.findUniqueOrThrow({ where: { id: guest.id } });
    expect(joined).toMatchObject({ workspaceId: owner.workspaceId, role: "member" });
    expect((await listMembers(owner.workspaceId)).map((m) => m.email).sort()).toEqual(["ana@example.com", "ben@example.com"]);

    const again = await user("cy@example.com");
    expect(await acceptInvitation(invite.token, again.id)).toMatchObject({ ok: false });
  });

  it("expired, revoked and made-up links don't work", async () => {
    const owner = await user("ana@example.com");
    const guest = await user("ben@example.com");
    const expired = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "viewer", -1);
    const revoked = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "viewer");
    if (!expired.ok || !revoked.ok) throw new Error("not created");
    await revokeInvitation(owner.workspaceId, revoked.invitation.id);
    for (const token of [expired.token, revoked.token, "inv_made_up"]) {
      expect(await acceptInvitation(token, guest.id)).toMatchObject({ ok: false });
    }
  });

  it("nobody hands out ownership by link, and members can't invite", async () => {
    const owner = await user("ana@example.com");
    expect(await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "owner")).toMatchObject({ ok: false });
    expect(await createInvitation(owner.workspaceId, { id: owner.id, role: "member" }, "viewer")).toMatchObject({ ok: false });
  });

  it("admins change roles but never the owner's; a removed member keeps an account of their own", async () => {
    const owner = await user("ana@example.com");
    const admin = await user("ben@example.com");
    const member = await user("cy@example.com");
    for (const [u, role] of [[admin, "admin"], [member, "member"]] as const) {
      const invite = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, role);
      if (!invite.ok) throw new Error(invite.error);
      await acceptInvitation(invite.token, u.id);
    }
    const asAdmin = { id: admin.id, role: "admin" as const };
    expect(await changeRole(owner.workspaceId, asAdmin, member.id, "viewer")).toMatchObject({ ok: true });
    expect(await changeRole(owner.workspaceId, asAdmin, owner.id, "member")).toMatchObject({ ok: false });
    expect(await removeMember(owner.workspaceId, asAdmin, owner.id)).toMatchObject({ ok: false });
    expect(await removeMember(owner.workspaceId, asAdmin, member.id)).toMatchObject({ ok: true });
    const removed = await db.user.findUniqueOrThrow({ where: { id: member.id } });
    expect(removed.workspaceId).not.toBe(owner.workspaceId);
    expect(removed.role).toBe("owner");
    expect(await db.auditLog.count({ where: { workspaceId: owner.workspaceId, action: { startsWith: "member." } } })).toBeGreaterThanOrEqual(3);
  });

  it("the owner can hand ownership to a member and becomes an admin", async () => {
    const owner = await user("ana@example.com");
    const admin = await user("ben@example.com");
    const invite = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "admin");
    if (!invite.ok) throw new Error(invite.error);
    await acceptInvitation(invite.token, admin.id);
    expect(await transferOwnership(owner.workspaceId, { id: admin.id, role: "admin" }, admin.id)).toMatchObject({ ok: false });
    expect(await transferOwnership(owner.workspaceId, { id: owner.id, role: "owner" }, admin.id)).toMatchObject({ ok: true });
    const roles = await db.user.findMany({ where: { workspaceId: owner.workspaceId }, orderBy: { email: "asc" } });
    expect(roles.map((u) => u.role)).toEqual(["admin", "owner"]);
  });

  it("an owner whose workspace has other members can't leave by accepting another invitation", async () => {
    const owner = await user("ana@example.com");
    const member = await user("ben@example.com");
    const inviteIn = await createInvitation(owner.workspaceId, { id: owner.id, role: "owner" }, "member");
    if (!inviteIn.ok) throw new Error(inviteIn.error);
    await acceptInvitation(inviteIn.token, member.id);
    const other = await user("cy@example.com");
    const inviteOut = await createInvitation(other.workspaceId, { id: other.id, role: "owner" }, "member");
    if (!inviteOut.ok) throw new Error(inviteOut.error);
    expect(await acceptInvitation(inviteOut.token, owner.id)).toMatchObject({ ok: false });
  });
});
