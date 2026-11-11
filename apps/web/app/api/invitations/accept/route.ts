import { acceptInvitation } from "@/lib/members";
import { currentContext } from "@/lib/workspace";

/** Join the invitation's workspace ({ token }). Any signed-in user may accept a valid link. */
export async function POST(request: Request) {
  const context = await currentContext();
  if (!context.signedIn || !context.userId) return Response.json({ error: "Sign in first." }, { status: 401 });
  const body = (await request.json().catch(() => ({}))) as { token?: unknown };
  if (typeof body.token !== "string") return Response.json({ error: "No invitation." }, { status: 400 });
  const result = await acceptInvitation(body.token, context.userId);
  return result.ok ? Response.json({ ok: true }) : Response.json({ error: result.error }, { status: 409 });
}
