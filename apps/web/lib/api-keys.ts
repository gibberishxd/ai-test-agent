/**
 * Workspace API keys for the public API (/api/v1), run 4, J3.
 *
 * - A key is "ata_" + 32 random bytes (base64url). It is shown once, when created.
 * - Only its SHA-256 hash is stored. A password needs a slow hash (bcrypt) because people pick
 *   guessable ones; a 256-bit random key can't be guessed, so a fast hash is enough, and the
 *   lookup is one indexed equality on `key_hash`.
 * - The first 12 characters (`prefix`) are kept in clear so people can tell keys apart.
 * - A revoked key stops working at once; `last_used_at` shows whether a key is still in use.
 * - Rate limit: a fixed one-minute window per key, counted in the database with one atomic
 *   INSERT ... ON CONFLICT, so it holds across several web servers.
 */
import { createHash, randomBytes } from "node:crypto";
import { db } from "@/lib/db";

export const KEY_PREFIX = "ata_";
const PREFIX_LENGTH = 12;
const LAST_USED_EVERY_MS = 60_000; // don't write last_used_at on every request
export const REQUESTS_PER_MINUTE = 60;

export type ApiKeyView = {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
};

export type ApiCaller = { workspaceId: string; keyId: string };

export function generateApiKey(): { key: string; prefix: string } {
  const key = KEY_PREFIX + randomBytes(32).toString("base64url");
  return { key, prefix: key.slice(0, PREFIX_LENGTH) };
}

export function hashApiKey(key: string): string {
  return createHash("sha256").update(key, "utf8").digest("hex");
}

export function bearerToken(headers: Headers): string | null {
  const match = /^Bearer\s+(\S+)\s*$/i.exec(headers.get("authorization") ?? "");
  return match ? match[1] : null;
}

type Row = Awaited<ReturnType<typeof db.apiKey.findFirstOrThrow>>;

function toView(row: Row): ApiKeyView {
  return {
    id: row.id,
    name: row.name,
    prefix: row.prefix,
    createdAt: row.createdAt.toISOString(),
    lastUsedAt: row.lastUsedAt?.toISOString() ?? null,
    revokedAt: row.revokedAt?.toISOString() ?? null,
  };
}

/** Returns the key itself once; afterwards only its view (name, prefix, dates) exists. */
export async function createApiKey(workspaceId: string, userId: string | null, name: string) {
  const { key, prefix } = generateApiKey();
  const row = await db.apiKey.create({
    data: { workspaceId, createdById: userId, name: name.trim().slice(0, 80) || "API key", prefix, keyHash: hashApiKey(key) },
  });
  return { key, view: toView(row) };
}

export async function listApiKeys(workspaceId: string): Promise<ApiKeyView[]> {
  const rows = await db.apiKey.findMany({ where: { workspaceId }, orderBy: { createdAt: "desc" } });
  return rows.map(toView);
}

export async function revokeApiKey(workspaceId: string, id: string): Promise<boolean> {
  const updated = await db.apiKey.updateMany({ where: { id, workspaceId, revokedAt: null }, data: { revokedAt: new Date() } });
  return updated.count > 0;
}

/** The workspace an `Authorization: Bearer ata_…` header belongs to, or null. */
export async function authenticateApiKey(headers: Headers): Promise<ApiCaller | null> {
  const token = bearerToken(headers);
  if (!token || !token.startsWith(KEY_PREFIX)) return null;
  const row = await db.apiKey.findUnique({ where: { keyHash: hashApiKey(token) } });
  if (!row || row.revokedAt) return null;
  if (!row.lastUsedAt || Date.now() - row.lastUsedAt.getTime() > LAST_USED_EVERY_MS) {
    await db.apiKey.update({ where: { id: row.id }, data: { lastUsedAt: new Date() } });
  }
  return { workspaceId: row.workspaceId, keyId: row.id };
}

/** Count this request in the key's current minute; refuse past `limit`. */
export async function rateLimit(
  keyId: string,
  limit = REQUESTS_PER_MINUTE,
  now = new Date(),
): Promise<{ ok: true } | { ok: false; retryAfterS: number }> {
  const windowStart = new Date(Math.floor(now.getTime() / 60_000) * 60_000);
  const [{ count }] = await db.$queryRaw<{ count: number }[]>`
    INSERT INTO api_rate_windows (api_key_id, window_start, count)
    VALUES (${keyId}::uuid, ${windowStart}, 1)
    ON CONFLICT (api_key_id, window_start) DO UPDATE SET count = api_rate_windows.count + 1
    RETURNING count`;
  if (count <= limit) return { ok: true };
  return { ok: false, retryAfterS: Math.ceil((windowStart.getTime() + 60_000 - now.getTime()) / 1000) };
}
