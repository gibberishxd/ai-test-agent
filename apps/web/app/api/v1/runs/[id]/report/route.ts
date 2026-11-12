import { apiReport, baseUrlOf, junitReport, withApiKey } from "@/lib/api-v1";
import { tenantDb } from "@/lib/tenant-db";
import { isUuid } from "@/lib/runs";

/** The run's findings as JSON, or as JUnit XML with ?format=junit (for CI test reports). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  return withApiKey(request, async (caller) => {
    const { id } = await params;
    const run = isUuid(id)
      ? await tenantDb(caller.workspaceId).run.findFirst({ where: { id, workspaceId: caller.workspaceId }, include: { bugs: { orderBy: { createdAt: "asc" } } } })
      : null;
    if (!run) return Response.json({ error: "Run not found." }, { status: 404 });
    const format = new URL(request.url).searchParams.get("format") ?? "json";
    if (format === "junit") {
      return new Response(junitReport(run), { headers: { "Content-Type": "application/xml; charset=utf-8" } });
    }
    if (format !== "json") return Response.json({ error: 'format is "json" or "junit".' }, { status: 400 });
    return Response.json(apiReport(run, baseUrlOf(request)));
  });
}
