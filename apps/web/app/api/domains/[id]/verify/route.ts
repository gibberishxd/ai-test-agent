import { checkDomain } from "@/lib/settings-data";
import { authorize } from "@/lib/workspace";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("domains.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  const result = await checkDomain(context.workspaceId, context.userId, id);
  if (!result.ok) return Response.json({ error: result.reason }, { status: 422 });
  return Response.json({ ok: true, method: result.method });
}
