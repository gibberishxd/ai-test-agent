import { requestResume } from "@/lib/deep";
import { can, forbidden } from "@/lib/roles";
import { currentContext } from "@/lib/workspace";

/** Resume a deep run that paused on a usage limit (run 9): it is queued again. */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in to resume a run." }, { status: 401 });
  if (context.role && !can(context.role, "run.start")) return forbidden("run.start");
  const resumed = await requestResume(context.workspaceId, id);
  if (!resumed) return Response.json({ error: "Run not found or not paused" }, { status: 409 });
  return Response.json({ ok: true });
}
