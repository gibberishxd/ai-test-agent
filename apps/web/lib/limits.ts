/** Limits on starting runs: monthly quota per workspace, and rules for visitors. Pure functions. */

export const VISITOR_RUNS_PER_HOUR = 5;

export function startOfMonth(now: Date): Date {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
}

export function quotaError(runsThisMonth: number, quota: number): string | null {
  if (runsThisMonth < quota) return null;
  return `This workspace has used its ${quota} runs for this month. The quota resets on the 1st.`;
}

export function visitorRateLimitError(recentRuns: number, limit = VISITOR_RUNS_PER_HOUR): string | null {
  if (recentRuns < limit) return null;
  return `Visitors can start ${limit} demo runs per hour. Sign in to run more.`;
}

export function visitorTargetError(isDemo: boolean): string | null {
  return isDemo ? null : "Sign in to test your own app. Visitors can test the demo shop.";
}

/** The client's IP from proxy headers (first hop), for the visitor rate limit. */
export function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || headers.get("x-real-ip") || "unknown";
}
