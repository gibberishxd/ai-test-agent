import { describe, expect, it } from "vitest";
import { clientIp, quotaError, startOfMonth, visitorRateLimitError, visitorTargetError } from "./limits";

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

  it("are identified by the first forwarded IP", () => {
    expect(clientIp(new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" }))).toBe("203.0.113.7");
    expect(clientIp(new Headers())).toBe("unknown");
  });
});
