import { addDomain } from "@/lib/settings-data";
import { currentContext } from "@/lib/workspace";

export async function POST(request: Request) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in to add domains." }, { status: 401 });
  const body = await request.json().catch(() => ({}));
  const result = await addDomain(context.workspaceId, String(body.hostname ?? ""));
  if (!result.ok) return Response.json({ error: result.error }, { status: 400 });
  return Response.json({ id: result.domain.id, hostname: result.domain.hostname }, { status: 201 });
}
