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
