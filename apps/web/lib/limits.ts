/** Limits on starting runs: monthly quota per workspace, and rules for visitors. Pure functions. */
import { SOCKET_ADDRESS_HEADER } from "@/lib/socket-address";

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

export type ProxyTrust = { trustProxy: boolean; hops: number };

/**
 * Whether a reverse proxy we control sits in front of the app (TRUST_PROXY=true), and how many
 * such proxies there are in a row (TRUSTED_PROXY_HOPS, default 1). Off unless set explicitly.
 */
export function proxyTrust(env: Record<string, string | undefined> = process.env): ProxyTrust {
  const hops = Number.parseInt(env.TRUSTED_PROXY_HOPS ?? "1", 10);
  return { trustProxy: env.TRUST_PROXY === "true", hops: Number.isInteger(hops) && hops > 0 ? hops : 1 };
}

/**
 * The client's IP, for the visitor rate limit.
 *
 * X-Forwarded-For is text anyone can send, so it's only read behind a proxy we trust, and then
 * only the entry that proxy wrote: each proxy appends the address it saw, so with `hops`
 * trusted proxies the real client is the `hops`-th entry from the right. Everything further
 * left came from the client. Without a trusted proxy the socket address is the client
 * (stamped on the request in instrumentation.ts); if that's missing too, all such requests
 * share the bucket "unknown", which is stricter, never looser.
 */
export function clientIp(headers: Headers, options: Partial<ProxyTrust> = proxyTrust()): string {
  const trust = { trustProxy: false, hops: 1, ...options };
  const socket = headers.get(SOCKET_ADDRESS_HEADER) || "unknown";
  if (!trust.trustProxy) return socket;
  const forwarded = (headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  return forwarded[forwarded.length - trust.hops] ?? socket;
}
