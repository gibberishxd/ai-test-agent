import { db } from "@/lib/db";
import { listLoginSetups, saveLoginSetup } from "@/lib/login-setups";
import { SecretBoxError, serverKey } from "@/lib/secret-box";
import { authorize, currentContext } from "@/lib/workspace";

/** The workspace's sign-in setups. Passwords and recorded sign-ins never leave the server. */
export async function GET() {
  const context = await currentContext();
  if (!context.signedIn) return Response.json({ setups: [] });
  return Response.json({ setups: await listLoginSetups(context.workspaceId) });
}

/** Create or replace the setup for a target (one per site). */
export async function POST(request: Request) {
  const auth = await authorize("login_setups.manage");
  if (!auth.ok) return auth.response;
  const context = auth.context;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  let key: Buffer;
  try {
    key = serverKey();
  } catch (error) {
    if (error instanceof SecretBoxError) return Response.json({ error: error.message }, { status: 500 });
    throw error;
  }
  const result = await saveLoginSetup(context.workspaceId, body, key);
  if (!result.ok) return Response.json({ errors: result.errors }, { status: 400 });
  await db.auditLog.create({
    data: {
      workspaceId: context.workspaceId,
      userId: context.userId,
      action: "login_setup.saved",
      metadata: { origin: result.setup.origin, kind: result.setup.kind },
    },
  });
  return Response.json({ setup: result.setup }, { status: 201 });
}
