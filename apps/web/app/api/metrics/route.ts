import { formatMetrics, readMetrics } from "@/lib/metrics";

/**
 * Prometheus metrics. If METRICS_TOKEN is set, the scraper must send it as a bearer token;
 * otherwise keep this path reachable only from the internal network (docs/DEPLOY.md).
 */
export async function GET(request: Request) {
  const token = process.env.METRICS_TOKEN;
  if (token && request.headers.get("authorization") !== `Bearer ${token}`) return new Response("Unauthorized", { status: 401 });
  return new Response(formatMetrics(await readMetrics()), { headers: { "Content-Type": "text/plain; version=0.0.4" } });
}
