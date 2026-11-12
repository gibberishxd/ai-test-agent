import { changeRole, removeMember } from "@/lib/members";
import { ROLES, type Role } from "@/lib/roles";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

/** Change a member's role ({ role }). Ownership moves only with POST …/owner. */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("members.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { role?: unknown };
  if (!isUuid(id) || !ROLES.includes(body.role as Role)) return Response.json({ error: "Send a member and a role." }, { status: 400 });
  const { context } = auth;
  const result = await changeRole(context.workspaceId, { id: context.userId!, role: context.role! }, id, body.role as Role);
  return result.ok ? Response.json({ ok: true }) : Response.json({ error: result.error }, { status: result.status ?? 403 });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("members.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!isUuid(id)) return Response.json({ error: "Member not found." }, { status: 404 });
  const { context } = auth;
  const result = await removeMember(context.workspaceId, { id: context.userId!, role: context.role! }, id);
  return result.ok ? Response.json({ ok: true }) : Response.json({ error: result.error }, { status: result.status ?? 403 });
}
