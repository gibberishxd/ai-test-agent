import { db } from "@/lib/db";
import { createShareLink, revokeShareLink } from "@/lib/share";
import { authorize } from "@/lib/workspace";

/** Create (or return the existing) read-only share link for a run. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("run.share");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  const token = await createShareLink(context.workspaceId, id);
  if (!token) return Response.json({ error: "Run not found" }, { status: 404 });
  await db.auditLog.create({
    data: { workspaceId: context.workspaceId, userId: context.userId, action: "share.created", runId: id },
  });
  return Response.json({ url: new URL(`/share/${token}`, request.url).toString() });
}

/** Revoke the share link: the old URL stops working. */
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("run.share");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const { id } = await params;
  if (!(await revokeShareLink(context.workspaceId, id))) {
    return Response.json({ error: "Run not found" }, { status: 404 });
  }
  await db.auditLog.create({
    data: { workspaceId: context.workspaceId, userId: context.userId, action: "share.revoked", runId: id },
  });
  return Response.json({ ok: true });
}
