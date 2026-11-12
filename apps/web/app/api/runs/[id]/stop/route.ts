import { can, forbidden } from "@/lib/roles";
import { requestStop } from "@/lib/runs";
import { currentContext } from "@/lib/workspace";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const context = await currentContext();
  if (context.signedIn && context.role && !can(context.role, "run.stop")) return forbidden("run.stop");
  const stopped = await requestStop(context.workspaceId, id);
  if (!stopped) return Response.json({ error: "Run not found or already finished" }, { status: 409 });
  return Response.json({ ok: true });
}
