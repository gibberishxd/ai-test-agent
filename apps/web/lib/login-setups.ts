/**
 * How the worker signs in to a workspace's target before the agent starts (run 4, J2).
 *
 * A TEST account only. Two kinds:
 * - "form": the worker opens the login page, fills username and password and submits.
 *   Selectors are optional; without them the worker finds the fields itself.
 * - "storage_state": a recorded sign-in (Playwright's storage state: cookies + local storage),
 *   for sites with SSO or two-factor login a script can't fill in.
 *
 * The password and the storage state are encrypted (lib/secret-box.ts, workspace id as
 * associated data) and nothing here ever returns them: views say only whether one is saved.
 */
import { db } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
import { encryptSecret } from "@/lib/secret-box";

export const LOGIN_KINDS = ["form", "storage_state"] as const;
export type LoginKind = (typeof LOGIN_KINDS)[number];

export const MAX_STORAGE_STATE_BYTES = 200_000;
const MAX_SELECTOR = 200;

export type LoginSetupInput = {
  origin: string;
  kind: LoginKind;
  loginUrl: string | null;
  username: string | null;
  /** null: keep the saved password (an edit that leaves the field empty). */
  password: string | null;
  usernameSelector: string | null;
  passwordSelector: string | null;
  submitSelector: string | null;
  successSelector: string | null;
  storageState: string | null;
};

export type LoginSetupErrors = Partial<Record<"targetUrl" | "kind" | "loginUrl" | "username" | "password" | "storageState" | "selectors", string>>;

export type LoginCheck = { ok: boolean; detail: string; checkedAt: string };

export type LoginSetupView = {
  id: string;
  origin: string;
  kind: string;
  loginUrl: string | null;
  username: string | null;
  passwordSaved: boolean;
  storageStateSaved: boolean;
  usernameSelector: string | null;
  passwordSelector: string | null;
  submitSelector: string | null;
  successSelector: string | null;
  /** A Test sign-in is waiting for the worker. */
  checking: boolean;
  lastCheck: LoginCheck | null;
};

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

function originOf(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.origin : null;
  } catch {
    return null;
  }
}

/** A Playwright storage state: { cookies: [...], origins: [...] } (both optional lists). */
function isStorageState(raw: string): boolean {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (typeof data !== "object" || data === null || Array.isArray(data)) return false;
    const listOrMissing = (value: unknown) => value === undefined || Array.isArray(value);
    return listOrMissing(data.cookies) && listOrMissing(data.origins) && ("cookies" in data || "origins" in data);
  } catch {
    return false;
  }
}

export function parseLoginSetupInput(
  body: Record<string, unknown>,
  saved: { passwordSaved: boolean },
): { ok: true; value: LoginSetupInput } | { ok: false; errors: LoginSetupErrors } {
  const errors: LoginSetupErrors = {};
  const origin = originOf(text(body.targetUrl));
  if (!origin) errors.targetUrl = "Enter the site's address, starting with https://.";
  const kind = text(body.kind) as LoginKind;
  if (!LOGIN_KINDS.includes(kind)) errors.kind = "Choose a login form or a recorded sign-in.";

  const selector = (name: string) => {
    const value = text(body[name]);
    if (value.length > MAX_SELECTOR) errors.selectors = `Selectors are at most ${MAX_SELECTOR} characters.`;
    return value || null;
  };
  let loginUrl: string | null = null;
  let username: string | null = null;
  let password: string | null = null;
  let storageState: string | null = null;
  if (kind === "form") {
    loginUrl = text(body.loginUrl) || null;
    if (!loginUrl || !originOf(loginUrl)) errors.loginUrl = "Enter the login page's address.";
    else if (origin && originOf(loginUrl) !== origin) errors.loginUrl = "The login page must be on the same site as the target.";
    username = text(body.username).slice(0, 200) || null;
    if (!username) errors.username = "Enter the test account's username or email.";
    // Passwords aren't trimmed: spaces can be part of one.
    password = typeof body.password === "string" && body.password !== "" ? body.password : null;
    if (!password && !saved.passwordSaved) errors.password = "Enter the test account's password.";
  } else if (kind === "storage_state") {
    storageState = text(body.storageState) || null;
    if (!storageState || !isStorageState(storageState)) {
      errors.storageState = "Paste a Playwright storage state: the JSON with cookies and origins.";
    } else if (Buffer.byteLength(storageState) > MAX_STORAGE_STATE_BYTES) {
      errors.storageState = "That recorded sign-in is too large (200 KB at most).";
    }
  }
  const selectors = {
    usernameSelector: kind === "form" ? selector("usernameSelector") : null,
    passwordSelector: kind === "form" ? selector("passwordSelector") : null,
    submitSelector: kind === "form" ? selector("submitSelector") : null,
    successSelector: selector("successSelector"),
  };
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, value: { origin: origin!, kind, loginUrl, username, password, ...selectors, storageState } };
}

type Row = Awaited<ReturnType<typeof db.loginSetup.findFirstOrThrow>>;

export function toView(row: Row): LoginSetupView {
  return {
    id: row.id,
    origin: row.origin,
    kind: row.kind,
    loginUrl: row.loginUrl,
    username: row.username,
    passwordSaved: Boolean(row.passwordCiphertext),
    storageStateSaved: Boolean(row.storageStateCiphertext),
    usernameSelector: row.usernameSelector,
    passwordSelector: row.passwordSelector,
    submitSelector: row.submitSelector,
    successSelector: row.successSelector,
    checking: row.checkRequestedAt !== null,
    lastCheck: (row.lastCheck as LoginCheck | null) ?? null,
  };
}

export async function listLoginSetups(workspaceId: string): Promise<LoginSetupView[]> {
  const rows = await tenantDb(workspaceId).loginSetup.findMany({ where: { workspaceId }, orderBy: { createdAt: "asc" } });
  return rows.map(toView);
}

/** Create or replace the setup for the target's origin. A new secret clears the last check. */
export async function saveLoginSetup(workspaceId: string, body: Record<string, unknown>, serverKey: Buffer) {
  const origin = originOf(text(body.targetUrl));
  const existing = origin ? await db.loginSetup.findUnique({ where: { workspaceId_origin: { workspaceId, origin } } }) : null;
  const parsed = parseLoginSetupInput(body, { passwordSaved: Boolean(existing?.passwordCiphertext) && existing?.kind === "form" });
  if (!parsed.ok) return parsed;
  const { password, storageState, ...fields } = parsed.value;
  const secrets = {
    passwordCiphertext:
      fields.kind !== "form" ? null : password ? encryptSecret(password, workspaceId, serverKey) : (existing?.passwordCiphertext ?? null),
    storageStateCiphertext: storageState ? encryptSecret(storageState, workspaceId, serverKey) : null,
  };
  const row = await db.loginSetup.upsert({
    where: { workspaceId_origin: { workspaceId, origin: fields.origin } },
    create: { workspaceId, ...fields, ...secrets },
    update: { ...fields, ...secrets, checkRequestedAt: null },
  });
  // The old result was for the old settings; Prisma can't set JSON to SQL NULL in an update.
  await db.$executeRaw`UPDATE login_setups SET last_check = NULL WHERE id = ${row.id}::uuid AND workspace_id = ${workspaceId}::uuid`;
  return { ok: true as const, setup: toView({ ...row, lastCheck: null, checkRequestedAt: null }) };
}

export async function deleteLoginSetup(workspaceId: string, id: string): Promise<boolean> {
  return (await db.loginSetup.deleteMany({ where: { id, workspaceId } })).count > 0;
}

/** "Test sign-in": the worker picks it up, signs in once and stores ok/failed. */
export async function requestLoginCheck(workspaceId: string, id: string): Promise<LoginSetupView | null> {
  const updated = await db.loginSetup.updateMany({ where: { id, workspaceId }, data: { checkRequestedAt: new Date() } });
  if (updated.count === 0) return null;
  return toView(await db.loginSetup.findFirstOrThrow({ where: { id, workspaceId } }));
}
