import { SecretBoxError, serverKey } from "@/lib/secret-box";
import { createWebhook, listWebhooks } from "@/lib/webhooks";
import { authorize, currentContext } from "@/lib/workspace";

export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ webhooks: [] });
  return Response.json({ webhooks: await listWebhooks(context.workspaceId) });
}

/** Add an endpoint. The response is the only time its signing secret is shown. */
export async function POST(request: Request) {
  const auth = await authorize("webhooks.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const body = (await request.json().catch(() => ({}))) as { url?: unknown };
  let key: Buffer;
  try {
    key = serverKey();
  } catch (error) {
    if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
    throw error;
  }
  const created = await createWebhook(context, typeof body.url === "string" ? body.url : "", key);
  if (!created.ok) return Response.json({ errors: { url: created.error } }, { status: 400 });
  return Response.json({ secret: created.secret, webhook: created.webhook }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
