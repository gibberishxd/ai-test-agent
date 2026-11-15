/**
 * The requirement a finding breaks (run 7, M3), from its evidence: the worker stores
 * `evidence.spec` when the agent cites a requirement it was shown ([S2]). Client-safe: the bug
 * card imports it.
 */
export function violatedSpec(evidence: Record<string, unknown>): { title: string; heading: string } | null {
  const spec = evidence.spec as { title?: unknown; heading?: unknown } | undefined;
  if (!spec || typeof spec !== "object" || typeof spec.title !== "string") return null;
  return { title: spec.title, heading: typeof spec.heading === "string" ? spec.heading : spec.title };
}
