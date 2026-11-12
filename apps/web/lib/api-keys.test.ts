import { describe, expect, it } from "vitest";
import { bearerToken, generateApiKey, hashApiKey, KEY_PREFIX } from "./api-keys";

describe("API keys", () => {
  it("are long random tokens with a recognisable prefix", () => {
    const a = generateApiKey();
    const b = generateApiKey();
    expect(a.key.startsWith(KEY_PREFIX)).toBe(true);
    expect(a.key.length).toBeGreaterThanOrEqual(40);
    expect(a.key).not.toBe(b.key);
    expect(a.prefix).toBe(a.key.slice(0, 12));
  });

  it("are stored as a SHA-256 hash, never as themselves", () => {
    const { key } = generateApiKey();
    const hash = hashApiKey(key);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
    expect(hash).not.toContain(key.slice(4));
    expect(hashApiKey(key)).toBe(hash);
  });

  it("are read from 'Authorization: Bearer …' only", () => {
    expect(bearerToken(new Headers({ authorization: "Bearer ata_abc" }))).toBe("ata_abc");
    expect(bearerToken(new Headers({ authorization: "bearer   ata_abc " }))).toBe("ata_abc");
    expect(bearerToken(new Headers({ authorization: "Basic xyz" }))).toBeNull();
    expect(bearerToken(new Headers())).toBeNull();
  });
});
