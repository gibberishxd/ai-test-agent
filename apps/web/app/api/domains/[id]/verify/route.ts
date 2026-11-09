import { checkDomain } from "@/lib/settings-data";
import { currentContext } from "@/lib/workspace";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in first." }, { status: 401 });
  const { id } = await params;
  const result = await checkDomain(context.workspaceId, context.userId, id);
  if (!result.ok) return Response.json({ error: result.reason }, { status: 422 });
  return Response.json({ ok: true, method: result.method });
}
