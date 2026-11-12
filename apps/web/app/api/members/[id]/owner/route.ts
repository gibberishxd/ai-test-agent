import { transferOwnership } from "@/lib/members";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

/** The owner hands ownership to this member and becomes an admin. */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("workspace.transfer");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!isUuid(id)) return Response.json({ error: "Member not found." }, { status: 404 });
  const { context } = auth;
  const result = await transferOwnership(context.workspaceId, { id: context.userId!, role: context.role! }, id);
  return result.ok ? Response.json({ ok: true }) : Response.json({ error: result.error }, { status: result.status ?? 403 });
}
