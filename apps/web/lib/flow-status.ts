/**
 * How a critical flow's result reads in the app (run 7, M4). Client-safe: the run report and the
 * Flows tab both import it.
 */
export const FLOW_STATUSES = {
  passed: { label: "Passed (script saved)", good: true },
  replayed: { label: "Passed by replay (no model)", good: true },
  repaired: { label: "Repaired (page changed, script updated)", good: true },
  failed: { label: "Failed", good: false },
  skipped: { label: "Skipped (no budget left)", good: false },
} as const;

export function flowStatus(status: string | null): { label: string; good: boolean | null } {
  if (!status) return { label: "Not run yet", good: null };
  return (FLOW_STATUSES as Record<string, { label: string; good: boolean }>)[status] ?? { label: status, good: null };
}
