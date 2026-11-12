import { db } from "@/lib/db";
import { storeProbe, toView } from "@/lib/model-configs";
import { probeModel, realProbeDeps } from "@/lib/model-probe";
import { isUuid } from "@/lib/runs";
import { SecretBoxError, decryptSecret, serverKey } from "@/lib/secret-box";
import { authorize } from "@/lib/workspace";

/** "Test connection": does the model answer, call a tool and read an image? The result is kept. */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("models.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  const row = isUuid(id) ? await db.modelConfig.findFirst({ where: { id, workspaceId: context.workspaceId } }) : null;
  if (!row) return Response.json({ error: "Model not found." }, { status: 404 });

  let apiKey: string | null = null;
  if (row.apiKeyCiphertext) {
    try {
      apiKey = decryptSecret(row.apiKeyCiphertext, context.workspaceId, serverKey());
    } catch (error) {
      if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
      throw error;
    }
  }
  const probe = await probeModel(
    { provider: row.provider, baseUrl: row.baseUrl, model: row.model, apiKey },
    realProbeDeps(),
  );
  await storeProbe(context, id, probe);
  return Response.json({ model: toView({ ...row, probe }) });
}
