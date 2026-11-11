import { listInvitations, listMembers } from "@/lib/members";
import { authorize } from "@/lib/workspace";

export async function GET() {
  const auth = await authorize("settings.view");
  if (!auth.ok) return auth.response;
  return Response.json({ members: await listMembers(auth.context.workspaceId), invitations: await listInvitations(auth.context.workspaceId) });
}
