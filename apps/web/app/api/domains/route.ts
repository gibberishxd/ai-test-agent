import { addDomain } from "@/lib/settings-data";
import { authorize } from "@/lib/workspace";

export async function POST(request: Request) {
  const auth = await authorize("domains.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const body = await request.json().catch(() => ({}));
  const result = await addDomain(context.workspaceId, String(body.hostname ?? ""));
  if (!result.ok) return Response.json({ error: result.error }, { status: 400 });
  return Response.json({ id: result.domain.id, hostname: result.domain.hostname }, { status: 201 });
}
