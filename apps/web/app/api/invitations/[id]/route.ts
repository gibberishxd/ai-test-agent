import { revokeInvitation } from "@/lib/members";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("members.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!isUuid(id) || !(await revokeInvitation(auth.context.workspaceId, id))) return Response.json({ error: "Invitation not found." }, { status: 404 });
  return Response.json({ ok: true });
}
