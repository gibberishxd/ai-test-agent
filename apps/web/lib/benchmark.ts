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
};

export type PerBug = { id: number; title: string; foundRuns: number };

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

export function perBug(row: BenchmarkRow): PerBug[] {
  const details = (row.details ?? {}) as { per_bug?: Record<string, { title: string; found_runs: number }> };
  return Object.entries(details.per_bug ?? {})
    .map(([id, value]) => ({ id: Number(id), title: value.title, foundRuns: value.found_runs }))
    .sort((a, b) => a.id - b.id);
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
