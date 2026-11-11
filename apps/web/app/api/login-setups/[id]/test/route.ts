import { requestLoginCheck } from "@/lib/login-setups";
import { isUuid } from "@/lib/runs";
import { currentContext } from "@/lib/workspace";

/**
 * "Test sign-in": asks the worker to sign in once with the saved setup (it needs a browser, so
 * the web app can't do it itself). Poll GET /api/login-setups for `checking` and `lastCheck`.
 */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ error: "Sign in first." }, { status: 401 });
  const { id } = await params;
  const setup = isUuid(id) ? await requestLoginCheck(context.workspaceId, id) : null;
  if (!setup) return Response.json({ error: "Sign-in setup not found." }, { status: 404 });
  return Response.json({ setup }, { status: 202 });
}
