import { getRun } from "@/lib/runs";
import { serializeRun } from "@/lib/serialize";
import { currentWorkspaceId } from "@/lib/workspace";

/** "Download JSON": the whole run (summary, steps, bugs) as a file. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await getRun(await currentWorkspaceId(), id);
  if (!run) return Response.json({ error: "Run not found" }, { status: 404 });
  return new Response(JSON.stringify(serializeRun(run), null, 2), {
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="ai-test-agent-run-${run.id}.json"`,
    },
  });
}
