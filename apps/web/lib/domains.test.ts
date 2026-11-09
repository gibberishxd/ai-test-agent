import { describe, expect, it, vi } from "vitest";
import { isPublicIp, normalizeHostname, verifyDomain, type VerifyDeps } from "./domains";

const TOKEN = "abc123";

function deps(overrides: Partial<VerifyDeps> = {}): VerifyDeps {
  return {
    resolveTxt: async () => [],
    resolveIps: async () => ["93.184.215.14"],
    fetchText: async () => null,
    ...overrides,
  };
}

describe("normalizeHostname", () => {
  it("accepts URLs and bare hostnames", () => {
    expect(normalizeHostname("https://Shop.Example.com/cart")).toBe("shop.example.com");
    expect(normalizeHostname("shop.example.com")).toBe("shop.example.com");
  });

  it("rejects things that aren't domains", () => {
    expect(normalizeHostname("localhost")).toBeNull();
    expect(normalizeHostname("10.0.0.1")).toBeNull();
    expect(normalizeHostname("")).toBeNull();
  });
});

describe("verifyDomain", () => {
  it("passes with the DNS TXT record", async () => {
    const result = await verifyDomain("shop.test", TOKEN, deps({ resolveTxt: async () => [[`ai-test-agent-verification=${TOKEN}`]] }));
    expect(result).toEqual({ ok: true, method: "dns" });
  });

  it("passes with the well-known file", async () => {
    const fetchText = vi.fn(async () => `${TOKEN}\n`);
    const result = await verifyDomain("shop.test", TOKEN, deps({ fetchText }));
    expect(result).toEqual({ ok: true, method: "file" });
    expect(fetchText).toHaveBeenCalledWith("https://shop.test/.well-known/ai-test-agent.txt");
  });

  it("fails with a wrong token, explaining both options", async () => {
    const result = await verifyDomain("shop.test", TOKEN, deps({ fetchText: async () => "other" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/TXT record.*well-known/);
  });

  it("never fetches from a host that resolves to a private address (SSRF)", async () => {
    const fetchText = vi.fn(async () => TOKEN);
    const result = await verifyDomain("evil.test", TOKEN, deps({ resolveIps: async () => ["169.254.169.254"], fetchText }));
    expect(result.ok).toBe(false);
    expect(fetchText).not.toHaveBeenCalled();
  });
});

describe("isPublicIp", () => {
  it.each(["10.1.2.3", "127.0.0.1", "169.254.169.254", "172.20.0.1", "192.168.1.1", "100.64.0.1", "::1", "fd00::1", "fe80::1", "::ffff:10.0.0.1"])(
    "%s is not public",
    (ip) => expect(isPublicIp(ip)).toBe(false),
  );

  it("public addresses are public", () => {
    expect(isPublicIp("93.184.215.14")).toBe(true);
    expect(isPublicIp("2606:2800:220:1::1")).toBe(true);
  });
});
