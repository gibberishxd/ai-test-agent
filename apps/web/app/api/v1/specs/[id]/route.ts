import { withApiKey } from "@/lib/api-v1";
import { deleteSpec, updateSpec } from "@/lib/target-specs";

type Params = { params: Promise<{ id: string }> };

/** Replace a spec's title and body (it is embedded again before the next run). */
export async function PATCH(request: Request, { params }: Params) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body || typeof body !== "object") return Response.json({ error: "Send a JSON body." }, { status: 400 });
    const result = await updateSpec(caller.workspaceId, id, body);
    if (!result.ok) {
      if ("notFound" in result) return Response.json({ error: "Spec not found." }, { status: 404 });
      return Response.json({ errors: result.errors }, { status: 400 });
    }
    return Response.json({ spec: result.spec });
  });
}

export async function DELETE(request: Request, { params }: Params) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    if (!(await deleteSpec(caller.workspaceId, id))) return Response.json({ error: "Spec not found." }, { status: 404 });
    return new Response(null, { status: 204 });
  });
}
