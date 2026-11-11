import { isUuid } from "@/lib/runs";
import { setTriage } from "@/lib/triage";
import { currentContext } from "@/lib/workspace";

/** Mark a finding confirmed, false positive or won't fix ({ state, comment }). It follows the
 *  finding (by fingerprint) into later runs of the same site. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in to triage findings." }, { status: 401 });
  const { id } = await params;
  if (!isUuid(id)) return Response.json({ error: "Finding not found." }, { status: 404 });
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await setTriage(context.workspaceId, context.userId, id, body);
  if (!result.ok) return Response.json({ error: result.error }, { status: result.status });
  return Response.json({ triage: result.triage });
}
