import { db } from "@/lib/db";
import { revokeInvitation } from "@/lib/members";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("members.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!isUuid(id) || !(await revokeInvitation(auth.context.workspaceId, id))) return Response.json({ error: "Invitation not found." }, { status: 404 });
  await db.auditLog.create({ data: { workspaceId: auth.context.workspaceId, userId: auth.context.userId, action: "member.invitation_revoked", metadata: { id } } });
  return Response.json({ ok: true });
}
