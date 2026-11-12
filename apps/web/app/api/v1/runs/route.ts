import { apiErrorNames, apiStatus, baseUrlOf, parseApiRunInput, withApiKey } from "@/lib/api-v1";
import { tenantDb } from "@/lib/tenant-db";
import { clientIp } from "@/lib/limits";
import { startRun } from "@/lib/runs";

/** Start a run. Same rules as the dashboard: quota, verified domains for interactive, models. */
export async function POST(request: Request) {
  return withApiKey(request, async (caller) => {
    const raw = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!raw || typeof raw !== "object") return Response.json({ error: "Send a JSON body." }, { status: 400 });
    const parsed = parseApiRunInput(raw);
    if (!parsed.ok) return Response.json({ errors: parsed.errors }, { status: 400 });
    const { body, maxSteps, maxSeconds } = parsed.value;
    // An API key acts with member rights: it starts and reads runs, it manages nothing.
    const context = { workspaceId: caller.workspaceId, userId: null, signedIn: true, role: "member" as const };
    const started = await startRun(context, body, clientIp(request.headers), { apiKeyId: caller.keyId, maxSteps, maxSeconds });
    if (!started.ok) return Response.json({ errors: apiErrorNames(started.errors) }, { status: started.status });
    const run = await tenantDb(caller.workspaceId).run.findUniqueOrThrow({ where: { id: started.id }, include: { bugs: true } });
    const status = apiStatus(run, baseUrlOf(request));
    return Response.json(status, { status: 201, headers: { Location: status.links.self } });
  });
}
