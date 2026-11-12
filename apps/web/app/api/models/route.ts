import { db } from "@/lib/db";
import { createModelConfig, listModelConfigs } from "@/lib/model-configs";
import { SecretBoxError, serverKey } from "@/lib/secret-box";
import { currentContext } from "@/lib/workspace";

/** The workspace's models. Keys never leave the server: only "•••• last4". */
export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ models: [] });
  return Response.json({ models: await listModelConfigs(context.workspaceId) });
}

export async function POST(request: Request) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in to add models." }, { status: 401 });
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  let key: Buffer;
  try {
    key = serverKey();
  } catch (error) {
    if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
    throw error;
  }
  const result = await createModelConfig(context.workspaceId, body, key);
  if (!result.ok) return Response.json({ errors: result.errors }, { status: 400 });
  await db.auditLog.create({
    data: {
      workspaceId: context.workspaceId,
      userId: context.userId,
      action: "model.added",
      metadata: { model: result.model.model, provider: result.model.provider },
    },
  });
  return Response.json({ model: result.model }, { status: 201 });
}
