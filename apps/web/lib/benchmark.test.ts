import { describe, expect, it } from "vitest";
import {
  commitLabel,
  decisions,
  holdout,
  judgeLabel,
  leaderboard,
  leaderboardFromView,
  latestPerProvider,
  reviewerLabel,
  perBug,
  percent,
  percentOrDash,
  trend,
  validResults,
  verification,
  type BenchmarkRow,
} from "./benchmark";

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
    aiRecall: null,
    holdoutRunsBuggy: null,
    holdoutRecall: null,
    holdoutAiRecall: null,
    holdoutPrecision: null,
    holdoutFalseAlarms: null,
    judge: null,
    rescoreCommit: null,
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
      { id: 1, title: "A", foundRuns: 3, needsJudgement: null }, // old row: not recorded
      { id: 2, title: "B", foundRuns: 0, needsJudgement: null },
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

describe("honest numbers", () => {
  it("says which planted bugs need judgement", () => {
    const details = { per_bug: { "1": { title: "A", found_runs: 3, detection: "deterministic" }, "5": { title: "E", found_runs: 0, detection: "agent" } } };
    expect(perBug(row({ details })).map((b) => b.needsJudgement)).toEqual([false, true]);
  });

  it("shows a dash, not 0%, for numbers an old row didn't record", () => {
    expect(percentOrDash(null)).toBe("—");
    expect(percentOrDash(0)).toBe("0%");
    expect(percentOrDash(0.125)).toBe("13%");
  });

  it("names the judge, or says it wasn't recorded", () => {
    expect(judgeLabel(row({ judge: "ollama/gemma4:12b" }))).toBe("ollama/gemma4:12b");
    expect(judgeLabel(row({ details: { judge: "claude/haiku" } }))).toBe("claude/haiku");
    expect(judgeLabel(row({}))).toBe("not recorded");
  });

  it("keeps the runs' commit and adds the rescore commit", () => {
    expect(commitLabel(row({ gitCommit: "abc1234" }))).toBe("abc1234");
    expect(commitLabel(row({ gitCommit: "abc1234", rescoreCommit: "def5678" }))).toBe(
      "abc1234 (rescored at def5678)",
    );
  });

  it("reads the holdout scores when they were measured", () => {
    expect(holdout(row({}))).toBeNull();
    const measured = row({ holdoutRunsBuggy: 2, holdoutRecall: 0.5, holdoutAiRecall: 0.25, holdoutPrecision: 1, holdoutFalseAlarms: 0 });
    expect(holdout(measured)).toEqual({ runsBuggy: 2, recall: 0.5, aiRecall: 0.25, precision: 1, falseAlarms: 0 });
  });
});

describe("leaderboard", () => {
  it("ranks each provider and model by AI-only recall, then overall recall; unknown last", () => {
    const strong = row({ id: "strong", provider: "claude", model: "sonnet", aiRecall: 0.6, recall: 0.7 });
    const weak = row({ id: "weak", provider: "ollama", model: "gemma", aiRecall: 0.13, recall: 0.42 });
    const tie = row({ id: "tie", provider: "openai-compat", model: "x", aiRecall: 0.13, recall: 0.5 });
    const old = row({ id: "old", provider: "ollama", model: "qwen", aiRecall: null, recall: 0.33 });
    const superseded = row({ id: "older-strong", provider: "claude", model: "sonnet", aiRecall: 0.9, createdAt: new Date("2026-11-01") });
    expect(leaderboard([weak, old, superseded, strong, tie]).map((r) => r.id)).toEqual(["strong", "tie", "weak", "old"]);
  });
});

describe("leaderboard from the materialized view (run 5, K3)", () => {
  it("keeps the rows the view chose (one per model, judge and reviewer), best first", () => {
    const alone = row({ id: "alone", provider: "ollama", model: "gemma", aiRecall: 0.08, recall: 0.3 });
    const tiered = row({ id: "tiered", provider: "ollama", model: "gemma", aiRecall: 0.2, recall: 0.4, details: { reviewer: "ollama/qwen3:14b" } });
    const stale = row({ id: "stale", provider: "ollama", model: "gemma", aiRecall: 0.5 });
    const board = leaderboardFromView([alone, tiered, stale], ["alone", "tiered"]);
    expect(board.map((r) => r.id)).toEqual(["tiered", "alone"]);
  });

  it("names the reviewer of a tiered setup", () => {
    expect(reviewerLabel(row({ details: { reviewer: "ollama/qwen3:14b" } }))).toBe("ollama/qwen3:14b");
    expect(reviewerLabel(row({ details: {} }))).toBeNull();
  });
});

describe("verification", () => {
  const stored = {
    reported: 9,
    verified: 5,
    duplicates: 1,
    discarded_at_replay: 3,
    discard_reasons: { judge_said_no: 1, element_not_found: 2 },
    bugs_lost: 1,
    recall_before: 0.5,
    ai_recall_before: 0.25,
    false_alarms_before: 2,
    correct_but_discarded: 2,
  };

  it("reads what verification threw away, biggest reason first", () => {
    expect(verification(row({ details: { verification: stored } }))).toEqual({
      reported: 9,
      verified: 5,
      duplicates: 1,
      discardedAtReplay: 3,
      reasons: [
        ["element_not_found", 2],
        ["judge_said_no", 1],
      ],
      bugsLost: 1,
      recallBefore: 0.5,
      aiRecallBefore: 0.25,
      falseAlarmsBefore: 2,
      correctButDiscarded: 2,
    });
  });

  it("reads the holdout's numbers from the holdout details", () => {
    const details = { holdout: { verification: { ...stored, correct_but_discarded: 4 } } };
    expect(verification(row({ details }), "holdout")?.correctButDiscarded).toBe(4);
  });

  it("is null for results saved before it was recorded", () => {
    expect(verification(row({ details: {} }))).toBeNull();
    expect(verification(row({ details: null }))).toBeNull();
  });
});

describe("validResults", () => {
  it("leaves out a result marked invalid (kept in the database, with the reason)", () => {
    const good = row({ provider: "ollama", model: "gemma4:12b" });
    const bad = row({ provider: "fake", model: "fake-agent", details: { invalid: "runs taken by another worker" } });
    expect(validResults([good, bad])).toEqual([good]);
  });
});
