import { createFlow } from "@/lib/target-flows";
import { authorize } from "@/lib/workspace";

/** Add a critical flow to a target. The next run's agent completes it and saves its script. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createFlow(auth.context, id, body);
  if (!result.ok) {
    if ("notFound" in result) return Response.json({ error: "Target not found." }, { status: 404 });
    return Response.json({ errors: result.errors }, { status: 400 });
  }
  return Response.json({ flow: result.flow }, { status: 201 });
}
