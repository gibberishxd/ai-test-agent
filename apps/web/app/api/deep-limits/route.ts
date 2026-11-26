import { parseDeepLimits, saveDeepLimits } from "@/lib/deep";
import { can, forbidden } from "@/lib/roles";
import { currentContext } from "@/lib/workspace";

/** Set the workspace's deep-mode limits (run 9). Owners and admins, like models. */
export async function PUT(request: Request) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in first." }, { status: 401 });
  if (!context.role || !can(context.role, "models.manage")) return forbidden("models.manage");
  const body = (await request.json().catch(() => ({}))) as { steps?: unknown; minutes?: unknown };
  const parsed = parseDeepLimits(body);
  if (!parsed.ok) return Response.json({ errors: parsed.errors }, { status: 400 });
  await saveDeepLimits(context.workspaceId, context.userId, parsed.value);
  return Response.json({ ok: true, ...parsed.value });
}
