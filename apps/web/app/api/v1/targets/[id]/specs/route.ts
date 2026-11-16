import { withApiKey } from "@/lib/api-v1";
import { createSpec, getTarget, listSpecs } from "@/lib/target-specs";

type Params = { params: Promise<{ id: string }> };

/** A target's specs, with whether the worker has embedded their latest version. */
export async function GET(request: Request, { params }: Params) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    if (!(await getTarget(caller.workspaceId, id))) return Response.json({ error: "Target not found." }, { status: 404 });
    return Response.json({ specs: await listSpecs(caller.workspaceId, id) });
  });
}

/** Add a spec (title + Markdown or text body). Embedded before the next run on the target. */
export async function POST(request: Request, { params }: Params) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body || typeof body !== "object") return Response.json({ error: "Send a JSON body." }, { status: 400 });
    const result = await createSpec(caller.workspaceId, id, body);
    if (!result.ok) {
      if ("notFound" in result) return Response.json({ error: "Target not found." }, { status: 404 });
      return Response.json({ errors: result.errors }, { status: 400 });
    }
    return Response.json({ spec: result.spec }, { status: 201 });
  });
}
