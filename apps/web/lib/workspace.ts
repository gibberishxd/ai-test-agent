import { currentUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { demoWorkspaceId } from "@/lib/system-db";
import { can, forbidden, type Action, type Role } from "@/lib/roles";

export const PUBLIC_WORKSPACE_SLUG = "demo";

export type RequestContext = {
  workspaceId: string;
  userId: string | null;
  signedIn: boolean;
  /** The member's role in the workspace (null: a visitor). */
  role?: Role | null;
};

/** The shared workspace visitors use; they may only test the hosted demo shop. */
export async function publicWorkspaceId(): Promise<string> {
  return demoWorkspaceId(); // a database function: visitors have no workspace of their own
}

/**
 * Who is acting, and in which workspace. Signed-in users act in their own workspace; visitors
 * share the public demo workspace. Every data function is scoped by the workspaceId from here.
 */
export async function currentContext(): Promise<RequestContext> {
  const user = await currentUser();
  // The workspace and role come from the database on every request, not from the session: a
  // changed role or an accepted invitation applies at once. (Reading a user before the
  // workspace is known is the one read the web role may do across workspaces: sign-in.)
  const member = user ? await db.user.findUnique({ where: { id: user.id }, select: { workspaceId: true, role: true } }) : null;
  if (user && member) return { workspaceId: member.workspaceId, userId: user.id, signedIn: true, role: member.role };
  return { workspaceId: await publicWorkspaceId(), userId: null, signedIn: false, role: null };
}

/**
 * For a route: the signed-in member's context if their role allows `action`, otherwise the
 * response to return (401 not signed in, 403 role too low).
 */
export async function authorize(action: Action): Promise<{ ok: true; context: RequestContext } | { ok: false; response: Response }> {
  const context = await currentContext();
  if (!context.signedIn) return { ok: false, response: Response.json({ error: "Sign in first." }, { status: 401 }) };
  if (!can(context.role ?? null, action)) return { ok: false, response: forbidden(action) };
  return { ok: true, context };
}

export async function currentWorkspaceId(): Promise<string> {
  return (await currentContext()).workspaceId;
}
