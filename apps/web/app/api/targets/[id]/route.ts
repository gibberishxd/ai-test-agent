import { deleteTarget } from "@/lib/target-specs";
import { authorize } from "@/lib/workspace";

/** Remove a target with its specs and flows (runs and findings stay). */
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize("targets.manage");
  if (!auth.ok) return auth.response;
  const { id } = await params;
  if (!(await deleteTarget(auth.context, id))) return Response.json({ error: "Target not found." }, { status: 404 });
  return Response.json({ deleted: true });
}
