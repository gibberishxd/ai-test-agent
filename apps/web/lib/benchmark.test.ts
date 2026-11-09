import { describe, expect, it } from "vitest";
import { decisions, latestPerProvider, perBug, percent, trend, type BenchmarkRow } from "./benchmark";

function row(fields: Partial<BenchmarkRow>): BenchmarkRow {
  return {
    id: "x",
    provider: "claude",
    model: "claude-sonnet-5-5",
    gitCommit: "abc1234",
    runsBuggy: 3,
    recall: 0.5,
    precision: 0.8,
    falseAlarms: 1,
    avgCostUsd: 0.3,
    avgDurationS: 120,
    details: {},
    createdAt: new Date("2026-11-09T10:00:00Z"),
    ...fields,
  };
}

describe("latestPerProvider", () => {
  it("keeps the newest result per provider and model", () => {
    const old = row({ id: "old", createdAt: new Date("2026-11-01") });
    const recent = row({ id: "new", createdAt: new Date("2026-11-09") });
    const local = row({ id: "local", provider: "ollama", model: "qwen", createdAt: new Date("2026-11-05") });
    expect(latestPerProvider([old, local, recent]).map((r) => r.id)).toEqual(["new", "local"]);
  });
});

describe("perBug and decisions", () => {
  const details = {
    per_bug: { "2": { title: "B", found_runs: 0 }, "1": { title: "A", found_runs: 3 } },
    decisions: [{ run_id: "r", report: "x", page: "/", candidates: [1], matched: 1, reason: "same" }],
  };

  it("lists bugs in id order", () => {
    expect(perBug(row({ details }))).toEqual([
      { id: 1, title: "A", foundRuns: 3 },
      { id: 2, title: "B", foundRuns: 0 },
    ]);
  });

  it("returns the saved match decisions", () => {
    expect(decisions(row({ details }))[0].reason).toBe("same");
  });

  it("copes with empty details", () => {
    expect(perBug(row({ details: null }))).toEqual([]);
    expect(decisions(row({ details: null }))).toEqual([]);
  });
});

describe("trend", () => {
  it("orders oldest first and picks values", () => {
    const points = trend(
      [row({ gitCommit: "b", createdAt: new Date("2026-11-09") }), row({ gitCommit: "a", createdAt: new Date("2026-11-01") })],
      (r) => [r.recall, r.precision],
    );
    expect(points.map((p) => p.label)).toEqual(["a", "b"]);
    expect(points[0].values).toEqual([0.5, 0.8]);
  });
});

it("formats percentages", () => {
  expect(percent(0.416)).toBe("42%");
});
