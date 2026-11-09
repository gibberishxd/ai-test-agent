import { getRun } from "@/lib/runs";
import { serializeRun } from "@/lib/serialize";
import { currentWorkspaceId } from "@/lib/workspace";

/** The live run page polls this every 1.5 s while the run is queued or running. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await getRun(await currentWorkspaceId(), id);
  if (!run) return Response.json({ error: "Run not found" }, { status: 404 });
  return Response.json(serializeRun(run), { headers: { "Cache-Control": "no-store" } });
}
