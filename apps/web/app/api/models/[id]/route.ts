import { deleteModelConfig, replaceModelKey, setDefaultModel } from "@/lib/model-configs";
import { isUuid } from "@/lib/runs";
import { SecretBoxError, serverKey } from "@/lib/secret-box";
import { authorize } from "@/lib/workspace";

/** Replace the key ({ apiKey }) or make it the workspace default ({ isDefault: true }). */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("models.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!isUuid(id)) return Response.json({ error: "Model not found." }, { status: 404 });
  const body = (await request.json().catch(() => ({}))) as { apiKey?: unknown; isDefault?: unknown };

  if (body.isDefault === true) {
    if (!(await setDefaultModel(context, id))) {
      return Response.json({ error: "Model not found." }, { status: 404 });
    }
    return Response.json({ ok: true });
  }

  if (typeof body.apiKey === "string" && body.apiKey.trim()) {
    let key: Buffer;
    try {
      key = serverKey();
    } catch (error) {
      if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
      throw error;
    }
    const model = await replaceModelKey(context, id, body.apiKey, key);
    if (!model) return Response.json({ error: "Model not found." }, { status: 404 });
    return Response.json({ model });
  }
  return Response.json({ error: "Send a new apiKey, or isDefault: true." }, { status: 400 });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("models.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!isUuid(id) || !(await deleteModelConfig(context, id))) {
    return Response.json({ error: "Model not found." }, { status: 404 });
  }
  return Response.json({ ok: true });
}
