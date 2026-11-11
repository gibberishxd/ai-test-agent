import { baseUrlOf } from "@/lib/api-v1";
import { createInvitation } from "@/lib/members";
import { ROLES, type Role } from "@/lib/roles";
import { authorize } from "@/lib/workspace";

/** Create an invitation link for a role. The link is in this response only. */
export async function POST(request: Request) {
  const auth = await authorize("members.manage");
  if (!auth.ok) return auth.response;
  const body = (await request.json().catch(() => ({}))) as { role?: unknown };
  if (!ROLES.includes(body.role as Role)) return Response.json({ error: "Choose a role." }, { status: 400 });
  const { context } = auth;
  const result = await createInvitation(context.workspaceId, { id: context.userId!, role: context.role! }, body.role as Role);
  if (!result.ok) return Response.json({ error: result.error }, { status: 403 });
  const link = `${baseUrlOf(request)}/invite/${result.token}`;
  return Response.json({ link, invitation: result.invitation }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
