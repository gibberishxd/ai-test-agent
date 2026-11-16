import { deleteSpec, updateSpec } from "@/lib/target-specs";
import { authorize } from "@/lib/workspace";

/** Edit a spec: it is embedded again before the next run on its target. */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await updateSpec(auth.context, id, body);
  if (!result.ok) {
    if ("notFound" in result) return Response.json({ error: "Spec not found." }, { status: 404 });
    return Response.json({ errors: result.errors }, { status: 400 });
  }
  return Response.json({ spec: result.spec });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!(await deleteSpec(auth.context, id))) return Response.json({ error: "Spec not found." }, { status: 404 });
  return Response.json({ deleted: true });
}
