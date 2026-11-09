import { requestStop } from "@/lib/runs";
import { currentWorkspaceId } from "@/lib/workspace";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const stopped = await requestStop(await currentWorkspaceId(), id);
  if (!stopped) return Response.json({ error: "Run not found or already finished" }, { status: 409 });
  return Response.json({ ok: true });
}
