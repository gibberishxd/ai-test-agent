import { db } from "@/lib/db";

/**
 * The workspace the current request acts in.
 *
 * Until sign-in exists (M8), everyone shares one "demo" workspace. Every data function still
 * takes a workspaceId, so adding real users only changes this function.
 */
export async function currentWorkspaceId(): Promise<string> {
  const workspace = await db.workspace.upsert({
    where: { slug: "demo" },
    update: {},
    create: { name: "Demo workspace", slug: "demo" },
  });
  return workspace.id;
}
