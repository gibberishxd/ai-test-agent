import { revokeApiKey } from "@/lib/api-keys";
import { isUuid } from "@/lib/runs";
import { authorize } from "@/lib/workspace";

/** Revoke: the key stops working at once. The row stays, so the audit trail stays readable. */
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("api_keys.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!isUuid(id) || !(await revokeApiKey(context, id))) {
    return Response.json({ error: "API key not found (or already revoked)." }, { status: 404 });
  }
  return Response.json({ ok: true });
}
