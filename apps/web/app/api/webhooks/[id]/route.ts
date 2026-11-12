import { isUuid } from "@/lib/runs";
import { deleteWebhook, setWebhookEnabled } from "@/lib/webhooks";
import { authorize } from "@/lib/workspace";

/** Pause or resume an endpoint ({ enabled }). */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("webhooks.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { enabled?: unknown };
  if (typeof body.enabled !== "boolean") return Response.json({ error: "Send { enabled: true | false }." }, { status: 400 });
  if (!isUuid(id) || !(await setWebhookEnabled(context, id, body.enabled))) {
    return Response.json({ error: "Webhook not found." }, { status: 404 });
  }
  return Response.json({ ok: true });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("webhooks.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!isUuid(id) || !(await deleteWebhook(context, id))) return Response.json({ error: "Webhook not found." }, { status: 404 });
  return Response.json({ ok: true });
}
