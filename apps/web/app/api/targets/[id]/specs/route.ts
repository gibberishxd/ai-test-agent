import { createSpec } from "@/lib/target-specs";
import { authorize } from "@/lib/workspace";

/** Add a spec to a target. The worker embeds it before the next run on that target. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createSpec(auth.context, id, body);
  if (!result.ok) {
    if ("notFound" in result) return Response.json({ error: "Target not found." }, { status: 404 });
    return Response.json({ errors: result.errors }, { status: 400 });
  }
  return Response.json({ spec: result.spec }, { status: 201 });
}
