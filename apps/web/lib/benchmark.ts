/**
 * Shaping benchmark results for the benchmark page. Pure functions over plain objects, so the
 * page logic is unit-tested without a database.
 */

export type BenchmarkRow = {
  id: string;
  provider: string;
  model: string;
  gitCommit: string;
  runsBuggy: number;
  recall: number;
  precision: number;
  falseAlarms: number;
  avgCostUsd: number;
  avgDurationS: number;
  details: unknown;
  createdAt: Date;
  /** Recall over the bugs that need judgement only. Null on rows from before it was recorded. */
  aiRecall: number | null;
  holdoutRunsBuggy: number | null;
  holdoutRecall: number | null;
  holdoutAiRecall: number | null;
  holdoutPrecision: number | null;
  holdoutFalseAlarms: number | null;
  judge: string | null;
  rescoreCommit: string | null;
};

/** `needsJudgement`: the deterministic checks can't find it; only the AI can. */
export type PerBug = { id: number; title: string; foundRuns: number; needsJudgement: boolean | null };

export type HoldoutScores = {
  runsBuggy: number;
  recall: number;
  aiRecall: number | null;
  precision: number | null;
  falseAlarms: number | null;
};

export type MatchDecision = {
  run_id: string;
  report: string;
  page: string;
  candidates: number[];
  matched: number | null;
  reason: string;
};

/**
 * Results that count. A result marked `details.invalid` (with the reason) stays in the database,
 * since results are never deleted, but isn't shown: run 4's first J1 benchmark was processed by
 * a stray worker with the fake model, so its numbers say nothing about any model.
 */
export function validResults<T extends { details: unknown }>(rows: T[]): T[] {
  return rows.filter((row) => !(row.details as { invalid?: string } | null)?.invalid);
}

/** The newest result for each provider/model pair, newest first. */
export function latestPerProvider(rows: BenchmarkRow[]): BenchmarkRow[] {
  const seen = new Map<string, BenchmarkRow>();
  for (const row of [...rows].sort((a, b) => +b.createdAt - +a.createdAt)) {
    const key = `${row.provider}/${row.model}`;
    if (!seen.has(key)) seen.set(key, row);
  }
  return [...seen.values()];
}

type StoredPerBug = Record<string, { title: string; found_runs: number; detection?: string }>;

function toPerBug(stored: StoredPerBug | undefined): PerBug[] {
  return Object.entries(stored ?? {})
    .map(([id, value]) => ({
      id: Number(id),
      title: value.title,
      foundRuns: value.found_runs,
      needsJudgement: value.detection ? value.detection === "agent" : null,
    }))
    .sort((a, b) => a.id - b.id);
}

/**
 * One row per provider and model (its newest result), best first: by AI-only recall (the
 * part the model is responsible for), then overall recall. Rows that didn't record AI-only
 * recall go last rather than being ranked as 0%.
 */
export function leaderboard(rows: BenchmarkRow[]): BenchmarkRow[] {
  const rank = (row: BenchmarkRow) => row.aiRecall ?? -1;
  return latestPerProvider(rows).sort((a, b) => rank(b) - rank(a) || b.recall - a.recall);
}

export function perBug(row: BenchmarkRow): PerBug[] {
  return toPerBug((row.details as { per_bug?: StoredPerBug } | null)?.per_bug);
}

/** The holdout app's per-bug results, if the row measured the holdout. */
export function holdoutPerBug(row: BenchmarkRow): PerBug[] {
  return toPerBug((row.details as { holdout?: { per_bug?: StoredPerBug } } | null)?.holdout?.per_bug);
}

/** The holdout app's scores, or null when the row didn't measure it. */
export function holdout(row: BenchmarkRow): HoldoutScores | null {
  if (row.holdoutRunsBuggy === null || row.holdoutRecall === null) return null;
  return {
    runsBuggy: row.holdoutRunsBuggy,
    recall: row.holdoutRecall,
    aiRecall: row.holdoutAiRecall,
    precision: row.holdoutPrecision,
    falseAlarms: row.holdoutFalseAlarms,
  };
}

/** Who judged the matches. Older rows didn't record it. */
export function judgeLabel(row: BenchmarkRow): string {
  const fromDetails = (row.details as { judge?: string } | null)?.judge;
  return row.judge || fromDetails || "not recorded";
}

/** The commit the runs were made on, plus the rescore's commit when there was one. */
export function commitLabel(row: BenchmarkRow): string {
  return row.rescoreCommit ? `${row.gitCommit} (rescored at ${row.rescoreCommit})` : row.gitCommit;
}

export function decisions(row: BenchmarkRow): MatchDecision[] {
  const details = (row.details ?? {}) as { decisions?: MatchDecision[] };
  return details.decisions ?? [];
}

export type ChartPoint = { label: string; date: string; values: number[] };

/** Oldest first, for a left-to-right trend chart. `pick` chooses the plotted values. */
export function trend(rows: BenchmarkRow[], pick: (row: BenchmarkRow) => number[]): ChartPoint[] {
  return [...rows]
    .sort((a, b) => +a.createdAt - +b.createdAt)
    .map((row) => ({
      label: row.gitCommit,
      date: row.createdAt.toISOString(),
      values: pick(row),
    }));
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** A percentage, or a dash for a number that wasn't recorded (never a misleading 0%). */
export function percentOrDash(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : percent(value);
}

export type Verification = {
  reported: number;
  verified: number;
  duplicates: number;
  discardedAtReplay: number;
  /** Why reports were discarded at replay, biggest reason first. */
  reasons: [string, number][];
  /** Planted bugs a run found but lost entirely in verification. */
  bugsLost: number;
  recallBefore: number;
  aiRecallBefore: number;
  falseAlarmsBefore: number;
  /** Discarded reports that match a planted bug: high means verification is too strict. */
  correctButDiscarded: number;
};

type StoredVerification = {
  reported: number;
  verified: number;
  duplicates: number;
  discarded_at_replay: number;
  discard_reasons: Record<string, number>;
  bugs_lost: number;
  recall_before: number;
  ai_recall_before: number;
  false_alarms_before: number;
  correct_but_discarded: number;
};

/** What verification did in this result (shop, or the holdout app). Null on older rows. */
export function verification(row: BenchmarkRow, set: "shop" | "holdout" = "shop"): Verification | null {
  const details = (row.details ?? {}) as { verification?: StoredVerification; holdout?: { verification?: StoredVerification } };
  const v = set === "holdout" ? details.holdout?.verification : details.verification;
  if (!v || typeof v.reported !== "number") return null;
  return {
    reported: v.reported,
    verified: v.verified,
    duplicates: v.duplicates,
    discardedAtReplay: v.discarded_at_replay,
    reasons: Object.entries(v.discard_reasons ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
    bugsLost: v.bugs_lost,
    recallBefore: v.recall_before,
    aiRecallBefore: v.ai_recall_before,
    falseAlarmsBefore: v.false_alarms_before,
    correctButDiscarded: v.correct_but_discarded,
  };
}
