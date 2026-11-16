import { deleteFlow, updateFlow } from "@/lib/target-flows";
import { authorize } from "@/lib/workspace";

/** Rename a flow or reword its journey (a new wording drops its saved script). */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await updateFlow(auth.context, id, body);
  if (!result.ok) {
    if ("notFound" in result) return Response.json({ error: "Flow not found." }, { status: 404 });
    return Response.json({ errors: result.errors }, { status: 400 });
  }
  return Response.json({ flow: result.flow });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!(await deleteFlow(auth.context, id))) return Response.json({ error: "Flow not found." }, { status: 404 });
  return Response.json({ deleted: true });
}
