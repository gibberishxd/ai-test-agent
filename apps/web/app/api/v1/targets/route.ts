import { withApiKey } from "@/lib/api-v1";
import { listTargets, saveTarget } from "@/lib/target-specs";

/** The workspace's targets (run 7): apps it tests, by origin. */
export async function GET(request: Request) {
  return withApiKey(request, async (caller) => Response.json({ targets: await listTargets(caller.workspaceId) }));
}

/** Add a target by URL (only its origin is kept); returns the existing one for that origin. */
export async function POST(request: Request) {
  return withApiKey(request, async (caller) => {
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body || typeof body !== "object") return Response.json({ error: "Send a JSON body." }, { status: 400 });
    const result = await saveTarget(caller.workspaceId, body);
    if (!result.ok) return Response.json({ errors: result.errors }, { status: 400 });
    return Response.json({ target: result.target }, { status: 201 });
  });
}
