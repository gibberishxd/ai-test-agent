import { describe, expect, it } from "vitest";
import { costHint, formatCost, formatDuration, formatEstimate, hostOf, isFinal } from "./format";

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

describe("formatEstimate (run 6)", () => {
  it("always says it is an estimate, and shows small amounts to a tenth of a cent", () => {
    expect(formatEstimate(0.1234)).toBe("≈ $0.123 est.");
    expect(formatEstimate(2.5)).toBe("≈ $2.50 est.");
    expect(formatEstimate(0.0004)).toBe("< $0.001 est.");
    expect(formatEstimate(0)).toBe("$0 est.");
  });

  it("shows a dash when nothing was measured", () => {
    expect(formatEstimate(null)).toBe("—");
    expect(formatEstimate(undefined)).toBe("—");
  });
});

describe("costHint (run 6)", () => {
  it("adds the API-equivalent estimate when a run was charged less than it would cost", () => {
    const run = { provider: "claude-cli", model: "claude-haiku-5-5", costUsd: 0, estimatedCostUsd: 0.12 };
    expect(costHint(run)).toBe("claude-cli · claude-haiku-5-5 · API price ≈ $0.120 est.");
  });

  it("leaves a charged run's hint as it was", () => {
    const run = { provider: "claude", model: "claude-sonnet-5-5", costUsd: 0.5, estimatedCostUsd: 0.5 };
    expect(costHint(run)).toBe("claude · claude-sonnet-5-5");
    expect(costHint({ provider: null, model: null, costUsd: 0, estimatedCostUsd: 0 })).toBeUndefined();
  });
});
