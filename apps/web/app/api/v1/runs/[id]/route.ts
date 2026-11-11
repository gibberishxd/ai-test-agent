import { apiStatus, baseUrlOf, withApiKey } from "@/lib/api-v1";
import { tenantDb } from "@/lib/tenant-db";
import { isUuid } from "@/lib/runs";

/** A run's status and bug counts. Poll until `finished` is true. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    const run = isUuid(id) ? await tenantDb(caller.workspaceId).run.findFirst({ where: { id, workspaceId: caller.workspaceId }, include: { bugs: true } }) : null;
    if (!run) return Response.json({ error: "Run not found." }, { status: 404 });
    return Response.json(apiStatus(run, baseUrlOf(request)));
  });
}
