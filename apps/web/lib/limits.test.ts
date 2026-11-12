import { describe, expect, it } from "vitest";
import { clientIp, proxyTrust, quotaError, startOfMonth, visitorRateLimitError, visitorTargetError } from "./limits";

describe("quota", () => {
  it("allows runs under the quota and refuses at the quota", () => {
    expect(quotaError(49, 50)).toBeNull();
    expect(quotaError(50, 50)).toMatch(/used its 50 runs/);
  });

  it("counts from the first of the month (UTC)", () => {
    expect(startOfMonth(new Date("2026-11-09T05:00:00Z")).toISOString()).toBe("2026-11-01T00:00:00.000Z");
  });
});

describe("visitors", () => {
  it("are limited to a few demo runs per hour", () => {
    expect(visitorRateLimitError(4)).toBeNull();
    expect(visitorRateLimitError(5)).toMatch(/Sign in/);
  });

  it("may only test the demo shop", () => {
    expect(visitorTargetError(true)).toBeNull();
    expect(visitorTargetError(false)).toMatch(/Sign in to test your own app/);
  });

});

describe("client IP for the visitor rate limit", () => {
  const spoofed = new Headers({ "x-forwarded-for": "6.6.6.6", "x-socket-address": "203.0.113.7" });

  it("without a trusted proxy, ignores X-Forwarded-For and uses the socket address", () => {
    expect(clientIp(spoofed, { trustProxy: false })).toBe("203.0.113.7");
  });

  it("without a socket address, everyone shares one bucket rather than trusting the header", () => {
    expect(clientIp(new Headers({ "x-forwarded-for": "6.6.6.6" }), { trustProxy: false })).toBe("unknown");
  });

  it("behind a trusted proxy, uses the right-most hop: the one our proxy wrote", () => {
    // "6.6.6.6" is whatever the client claimed; our proxy appended the address it saw.
    const headers = new Headers({ "x-forwarded-for": "6.6.6.6, 198.51.100.4", "x-socket-address": "10.0.0.2" });
    expect(clientIp(headers, { trustProxy: true })).toBe("198.51.100.4");
  });

  it("with two trusted proxies in a row, skips the inner proxy's own entry", () => {
    const headers = new Headers({ "x-forwarded-for": "6.6.6.6, 198.51.100.4, 10.0.0.9" });
    expect(clientIp(headers, { trustProxy: true, hops: 2 })).toBe("198.51.100.4");
  });

  it("behind a trusted proxy that sent no header, falls back to the socket address", () => {
    expect(clientIp(new Headers({ "x-socket-address": "10.0.0.2" }), { trustProxy: true })).toBe("10.0.0.2");
  });

  it("reads TRUST_PROXY from the environment, off unless it is exactly 'true'", () => {
    expect(proxyTrust({})).toEqual({ trustProxy: false, hops: 1 });
    expect(proxyTrust({ TRUST_PROXY: "1" }).trustProxy).toBe(false);
    expect(proxyTrust({ TRUST_PROXY: "true", TRUSTED_PROXY_HOPS: "2" })).toEqual({ trustProxy: true, hops: 2 });
  });
});
