import { getRun } from "@/lib/runs";
import { serializeRun } from "@/lib/serialize";
import { runHistory } from "@/lib/triage";
import { currentWorkspaceId } from "@/lib/workspace";

/** The live run page polls this every 1.5 s while the run is queued or running. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const workspaceId = await currentWorkspaceId();
  const run = await getRun(workspaceId, id);
  if (!run) return Response.json({ error: "Run not found" }, { status: 404 });
  const view = { ...serializeRun(run), history: await runHistory(workspaceId, run) };
  return Response.json(view, { headers: { "Cache-Control": "no-store" } });
}
