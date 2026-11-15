/** Small display helpers shared by the dashboard, history and report pages. */

export function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return "< $0.01";
  return `$${usd.toFixed(2)}`;
}

/**
 * An API-equivalent cost estimate (run 6): what a run's calls would cost on the model's API at
 * list price, computed from token counts. Always labelled, so it is never read as a charge.
 */
export function formatEstimate(usd: number | null | undefined): string {
  if (usd == null) return "—";
  if (usd === 0) return "$0 est.";
  if (usd < 0.001) return "< $0.001 est.";
  return "≈ $" + usd.toFixed(usd < 1 ? 3 : 2) + " est.";
}

type CostedRun = { provider: string | null; model: string | null; costUsd: number; estimatedCostUsd: number };

/** The hint under a run's cost: provider · model, plus the estimate when it was charged less. */
export function costHint(run: CostedRun): string | undefined {
  const parts = run.model ? [run.provider + " · " + run.model] : [];
  if (run.estimatedCostUsd > run.costUsd) parts.push("API price " + formatEstimate(run.estimatedCostUsd));
  return parts.length ? parts.join(" · ") : undefined;
}

export function formatDuration(
  start: Date | string | null,
  end: Date | string | null,
  now: number = Date.now(),
): string {
  if (!start) return "—";
  const ms = (end ? new Date(end).getTime() : now) - new Date(start).getTime();
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

export function formatDate(date: Date | string): string {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(date),
  );
}

export function hostOf(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

export const FINAL_STATUSES = ["done", "failed", "stopped"] as const;

export function isFinal(status: string): boolean {
  return (FINAL_STATUSES as readonly string[]).includes(status);
}
