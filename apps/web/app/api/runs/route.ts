import { createRun, listRuns } from "@/lib/runs";
import { parseRunInput } from "@/lib/targets";
import { currentWorkspaceId } from "@/lib/workspace";

/** Start a run: validate, then insert it as "queued" for the worker to pick up. */
export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const parsed = parseRunInput(body);
  if (!parsed.ok) return Response.json({ errors: parsed.errors }, { status: 400 });

  const workspaceId = await currentWorkspaceId();
  const run = await createRun(workspaceId, null, parsed.value);
  return Response.json({ id: run.id }, { status: 201 });
}

export async function GET() {
  const workspaceId = await currentWorkspaceId();
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
