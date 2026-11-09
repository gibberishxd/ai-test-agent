/** Small display helpers shared by the dashboard, history and report pages. */

export function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return "< $0.01";
  return `$${usd.toFixed(2)}`;
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
