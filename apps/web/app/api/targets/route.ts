import { listTargets, saveTarget } from "@/lib/target-specs";
import { authorize, currentContext } from "@/lib/workspace";

/** The workspace's targets (run 7): apps it tests, by origin, with their specs and flows. */
export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ targets: [] });
  return Response.json({ targets: await listTargets(context.workspaceId) });
}

/** Add a target (or get the existing one for that origin). */
export async function POST(request: Request) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await saveTarget(auth.context, body);
  if (!result.ok) return Response.json({ errors: result.errors }, { status: 400 });
  return Response.json({ target: result.target }, { status: 201 });
}
