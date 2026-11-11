import { db } from "@/lib/db";
import { deleteLoginSetup } from "@/lib/login-setups";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("login_setups.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!isUuid(id) || !(await deleteLoginSetup(context.workspaceId, id))) {
    return Response.json({ error: "Sign-in setup not found." }, { status: 404 });
  }
  await db.auditLog.create({
    data: { workspaceId: context.workspaceId, userId: context.userId, action: "login_setup.deleted", metadata: { id } },
  });
  return Response.json({ ok: true });
}
