import { currentUser } from "@/lib/auth";
import { db } from "@/lib/db";

export const PUBLIC_WORKSPACE_SLUG = "demo";

export type RequestContext = {
  workspaceId: string;
  userId: string | null;
  signedIn: boolean;
};

/** The shared workspace visitors use; they may only test the hosted demo shop. */
export async function publicWorkspaceId(): Promise<string> {
  const workspace = await db.workspace.upsert({
    where: { slug: PUBLIC_WORKSPACE_SLUG },
    update: {},
    create: { name: "Public demo", slug: PUBLIC_WORKSPACE_SLUG },
  });
  return workspace.id;
}

/**
 * Who is acting, and in which workspace. Signed-in users act in their own workspace; visitors
 * share the public demo workspace. Every data function is scoped by the workspaceId from here.
 */
export async function currentContext(): Promise<RequestContext> {
  const user = await currentUser();
  if (user) return { workspaceId: user.workspaceId, userId: user.id, signedIn: true };
  return { workspaceId: await publicWorkspaceId(), userId: null, signedIn: false };
}

export async function currentWorkspaceId(): Promise<string> {
  return (await currentContext()).workspaceId;
}
