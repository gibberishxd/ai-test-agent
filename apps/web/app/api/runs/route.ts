import { clientIp } from "@/lib/limits";
import { listRuns, startRun } from "@/lib/runs";
import { currentContext } from "@/lib/workspace";

/** Start a run: every check runs in startRun, then the run is queued for the worker. */
export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const result = await startRun(await currentContext(), body, clientIp(request.headers));
  if (!result.ok) return Response.json({ errors: result.errors }, { status: result.status });
  return Response.json({ id: result.id }, { status: 201 });
}

export async function GET() {
  const { workspaceId } = await currentContext();
  const runs = await listRuns(workspaceId);
  return Response.json({
    runs: runs.map((run) => ({
      id: run.id,
      targetUrl: run.targetUrl,
      mode: run.mode,
      status: run.status,
      costUsd: run.costUsd,
      summary: run.summary,
      createdAt: run.createdAt,
    })),
  });
}
