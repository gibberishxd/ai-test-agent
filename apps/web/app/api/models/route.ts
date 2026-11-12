import { createModelConfig, listModelConfigs } from "@/lib/model-configs";
import { SecretBoxError, serverKey } from "@/lib/secret-box";
import { authorize, currentContext } from "@/lib/workspace";

/** The workspace's models. Keys never leave the server: only "•••• last4". */
export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ models: [] });
  return Response.json({ models: await listModelConfigs(context.workspaceId) });
}

export async function POST(request: Request) {
  const auth = await authorize("models.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  let key: Buffer;
  try {
    key = serverKey();
  } catch (error) {
    if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
    throw error;
  }
  const result = await createModelConfig(context, body, key);
  if (!result.ok) return Response.json({ errors: result.errors }, { status: 400 });
  return Response.json({ model: result.model }, { status: 201 });
}
