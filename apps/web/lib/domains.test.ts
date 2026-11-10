import { describe, expect, it, vi } from "vitest";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { fetchPinned, isPublicIp, normalizeHostname, pinnedLookup, verifyDomain, type VerifyDeps } from "./domains";

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
    // The fetch is told which address to connect to: the one that was just checked.
    expect(fetchText).toHaveBeenCalledWith("https://shop.test/.well-known/ai-test-agent.txt", "93.184.215.14");
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

describe("pinned fetch", () => {
  it("lookup answers with the pinned address whatever name is asked", () => {
    const calls: unknown[][] = [];
    const lookup = pinnedLookup("93.184.215.14");
    lookup("anything.test", {}, (...args: unknown[]) => calls.push(args));
    lookup("anything.test", { all: true }, (...args: unknown[]) => calls.push(args));
    expect(calls).toEqual([
      [null, "93.184.215.14", 4],
      [null, [{ address: "93.184.215.14", family: 4 }]],
    ]);
    expect(pinnedLookup("2606:2800:220:1::1")("x", {}, (...args: unknown[]) => calls.push(args))).toBeUndefined();
    expect(calls[2]).toEqual([null, "2606:2800:220:1::1", 6]);
  });

  it("connects to the pinned address, not to wherever the name resolves", async () => {
    // "rebind.invalid" never resolves, so a response proves the connection used the pin.
    const server = createServer((request, response) => response.end(`host=${request.headers.host}`));
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    try {
      const body = await fetchPinned(`http://rebind.invalid:${port}/.well-known/ai-test-agent.txt`, "127.0.0.1");
      expect(body).toBe(`host=rebind.invalid:${port}`);
    } finally {
      server.close();
    }
  });

  it("gives up on redirects, errors and oversized bodies", async () => {
    const server = createServer((request, response) => {
      if (request.url === "/redirect") response.writeHead(302, { Location: "http://169.254.169.254/" }).end();
      else if (request.url === "/big") response.end("x".repeat(5000));
      else response.writeHead(500).end("no");
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    try {
      expect(await fetchPinned(`http://site.invalid:${port}/redirect`, "127.0.0.1")).toBeNull();
      expect(await fetchPinned(`http://site.invalid:${port}/big`, "127.0.0.1")).toBeNull();
      expect(await fetchPinned(`http://site.invalid:${port}/error`, "127.0.0.1")).toBeNull();
    } finally {
      server.close();
    }
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
