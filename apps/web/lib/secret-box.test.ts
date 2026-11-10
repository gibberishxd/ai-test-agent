import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { SecretBoxError, decryptSecret, encryptSecret, lastFour, serverKey } from "./secret-box";

// The same vector is decrypted by the worker's test (apps/worker/tests/test_secret_box.py).
const VECTOR = JSON.parse(
  readFileSync(path.join(process.cwd(), "..", "worker", "tests", "fixtures", "secret_box_vector.json"), "utf8"),
) as { key_base64: string; workspace_id: string; plaintext: string; stored: string };
const KEY = Buffer.from(VECTOR.key_base64, "base64");
const NONCE = Buffer.from(Array.from({ length: 12 }, (_, i) => 100 + i));

describe("secret box", () => {
  it("matches the shared vector, so the worker can decrypt what the web stores", () => {
    expect(encryptSecret(VECTOR.plaintext, VECTOR.workspace_id, KEY, NONCE)).toBe(VECTOR.stored);
    expect(decryptSecret(VECTOR.stored, VECTOR.workspace_id, KEY)).toBe(VECTOR.plaintext);
  });

  it("never contains the key in readable form and differs every time", () => {
    const a = encryptSecret("sk-live-ABCD1234wxyz", "ws", KEY);
    const b = encryptSecret("sk-live-ABCD1234wxyz", "ws", KEY);
    expect(a).not.toContain("sk-live");
    expect(Buffer.from(a.slice(3), "base64").toString("latin1")).not.toContain("ABCD1234");
    expect(a).not.toBe(b);
  });

  it("doesn't decrypt in another workspace", () => {
    expect(() => decryptSecret(VECTOR.stored, "22222222-2222-4222-8222-222222222222", KEY)).toThrow(SecretBoxError);
  });

  it("doesn't decrypt with another server key, or after tampering", () => {
    const other = Buffer.alloc(32, 7);
    expect(() => decryptSecret(VECTOR.stored, VECTOR.workspace_id, other)).toThrow(SecretBoxError);
    const tampered = VECTOR.stored.slice(0, -6) + "AAAAA=";
    expect(() => decryptSecret(tampered, VECTOR.workspace_id, KEY)).toThrow(SecretBoxError);
  });

  it("refuses to work without a proper server key", () => {
    expect(() => serverKey({})).toThrow(/MODEL_KEYS_SECRET/);
    expect(() => serverKey({ MODEL_KEYS_SECRET: "c2hvcnQ=" })).toThrow(/32 random bytes/);
    expect(serverKey({ MODEL_KEYS_SECRET: VECTOR.key_base64 }).equals(KEY)).toBe(true);
  });

  it("shows only the last four characters", () => {
    expect(lastFour(" sk-live-ABCD1234wxyz ")).toBe("wxyz");
  });
});
