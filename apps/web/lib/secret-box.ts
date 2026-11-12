/**
 * Encrypting a workspace's model API key at rest: AES-256-GCM.
 *
 * - The server key comes from MODEL_KEYS_SECRET (32 random bytes, base64). Without it, keys
 *   can't be saved: there is no "store it in plain text" fallback.
 * - Each value gets a fresh 12-byte nonce. GCM also authenticates: a changed ciphertext fails
 *   to decrypt instead of decrypting to garbage.
 * - The workspace id is the associated data, so a ciphertext copied into another workspace's
 *   row doesn't decrypt there.
 * - Stored as "v1:" + base64(nonce ‖ ciphertext ‖ tag). The worker (Python, `cryptography`'s
 *   AESGCM) reads the same format; a shared test vector keeps the two in step.
 */
import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

const VERSION = "v1:";
const NONCE_BYTES = 12;
const TAG_BYTES = 16;

export class SecretBoxError extends Error {}

export function serverKey(env: Record<string, string | undefined> = process.env): Buffer {
  const raw = env.MODEL_KEYS_SECRET ?? "";
  const key = Buffer.from(raw, "base64");
  if (key.length !== 32) {
    throw new SecretBoxError(
      "MODEL_KEYS_SECRET must be 32 random bytes in base64 (e.g. `openssl rand -base64 32`) to store model API keys.",
    );
  }
  return key;
}

export function encryptSecret(plain: string, workspaceId: string, key: Buffer, nonce = randomBytes(NONCE_BYTES)): string {
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  cipher.setAAD(Buffer.from(workspaceId, "utf8"));
  const body = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return VERSION + Buffer.concat([nonce, body, cipher.getAuthTag()]).toString("base64");
}

export function decryptSecret(stored: string, workspaceId: string, key: Buffer): string {
  if (!stored.startsWith(VERSION)) throw new SecretBoxError("unknown secret format");
  const data = Buffer.from(stored.slice(VERSION.length), "base64");
  const nonce = data.subarray(0, NONCE_BYTES);
  const tag = data.subarray(data.length - TAG_BYTES);
  const body = data.subarray(NONCE_BYTES, data.length - TAG_BYTES);
  const decipher = createDecipheriv("aes-256-gcm", key, nonce);
  decipher.setAAD(Buffer.from(workspaceId, "utf8"));
  decipher.setAuthTag(tag);
  try {
    return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
  } catch {
    throw new SecretBoxError("the key can't be decrypted here (wrong workspace or server key)");
  }
}

/** What the UI may show of a key: its last four characters. */
export function lastFour(plain: string): string {
  return plain.trim().slice(-4);
}
