import { createApiKey, listApiKeys } from "@/lib/api-keys";
import { db } from "@/lib/db";
import { authorize, currentContext } from "@/lib/workspace";

export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ keys: [] });
  return Response.json({ keys: await listApiKeys(context.workspaceId) });
}

/** Create a key. The response is the only time the key itself is ever shown. */
export async function POST(request: Request) {
  const auth = await authorize("api_keys.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const body = (await request.json().catch(() => ({}))) as { name?: unknown };
  const created = await createApiKey(context.workspaceId, context.userId, typeof body.name === "string" ? body.name : "");
  await db.auditLog.create({
    data: { workspaceId: context.workspaceId, userId: context.userId, action: "api_key.created", metadata: { name: created.view.name, prefix: created.view.prefix } },
  });
  return Response.json({ key: created.key, apiKey: created.view }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
