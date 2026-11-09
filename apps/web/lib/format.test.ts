import { describe, expect, it } from "vitest";
import { formatCost, formatDuration, hostOf, isFinal } from "./format";

describe("formatCost", () => {
  it("shows tiny amounts honestly", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(0.004)).toBe("< $0.01");
    expect(formatCost(0.237)).toBe("$0.24");
  });
});

describe("formatDuration", () => {
  it("formats seconds and minutes", () => {
    const start = new Date("2026-11-09T10:00:00Z");
    expect(formatDuration(start, new Date("2026-11-09T10:00:42Z"))).toBe("42s");
    expect(formatDuration(start, new Date("2026-11-09T10:03:05Z"))).toBe("3m 05s");
    expect(formatDuration(null, null)).toBe("—");
  });
});

describe("helpers", () => {
  it("shortens URLs to host and path", () => {
    expect(hostOf("http://localhost:5173/")).toBe("localhost:5173");
    expect(hostOf("https://shop.test/cart")).toBe("shop.test/cart");
  });

  it("knows the final statuses", () => {
    expect(isFinal("done")).toBe(true);
    expect(isFinal("running")).toBe(false);
  });
});
