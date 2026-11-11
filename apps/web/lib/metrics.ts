/**
 * Prometheus metrics (run 4, J6), computed from the database: with several web servers and
 * workers, every server reports the same totals, and nothing is lost when a process restarts.
 */
import { db } from "@/lib/db";

export type MetricValues = {
  runsByStatus: Record<string, number>;
  queueDepth: number;
  runSecondsSum: number;
  runSecondsCount: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  webhookDeliveries: Record<string, number>;
};

function metric(name: string, type: "counter" | "gauge" | "summary", help: string, lines: string[]): string {
  return [`# HELP ${name} ${help}`, `# TYPE ${name} ${type}`, ...lines].join("\n");
}

export function formatMetrics(v: MetricValues): string {
  return (
    [
      metric("ata_runs_total", "counter", "Runs by status.", Object.entries(v.runsByStatus).map(([s, n]) => `ata_runs_total{status="${s}"} ${n}`)),
      metric("ata_queue_depth", "gauge", "Runs waiting for a worker.", [`ata_queue_depth ${v.queueDepth}`]),
      metric("ata_run_duration_seconds", "summary", "Duration of finished runs.", [
        `ata_run_duration_seconds_sum ${v.runSecondsSum}`,
        `ata_run_duration_seconds_count ${v.runSecondsCount}`,
      ]),
      metric("ata_model_tokens_total", "counter", "Model tokens used by runs.", [
        `ata_model_tokens_total{direction="input"} ${v.inputTokens}`,
        `ata_model_tokens_total{direction="output"} ${v.outputTokens}`,
      ]),
      metric("ata_model_cost_usd_total", "counter", "Model cost of runs in USD.", [`ata_model_cost_usd_total ${v.costUsd}`]),
      metric(
        "ata_webhook_deliveries",
        "gauge",
        "Webhook deliveries by status.",
        Object.entries(v.webhookDeliveries).map(([s, n]) => `ata_webhook_deliveries{status="${s}"} ${n}`),
      ),
    ].join("\n") + "\n"
  );
}

export async function readMetrics(): Promise<MetricValues> {
  const [statuses, totals, deliveries] = await Promise.all([
    db.run.groupBy({ by: ["status"], _count: { _all: true } }),
    db.$queryRaw<{ seconds: number | null; finished: bigint; input: bigint | null; output: bigint | null; cost: number | null }[]>`
      SELECT sum(extract(epoch FROM finished_at - started_at)) AS seconds,
             count(*) FILTER (WHERE finished_at IS NOT NULL AND started_at IS NOT NULL) AS finished,
             sum(input_tokens) AS input, sum(output_tokens) AS output, sum(cost_usd) AS cost
      FROM runs`,
    db.webhookDelivery.groupBy({ by: ["status"], _count: { _all: true } }),
  ]);
  const runsByStatus = Object.fromEntries(statuses.map((s) => [s.status, s._count._all]));
  const t = totals[0];
  return {
    runsByStatus,
    queueDepth: runsByStatus.queued ?? 0,
    runSecondsSum: Number(t?.seconds ?? 0),
    runSecondsCount: Number(t?.finished ?? 0),
    inputTokens: Number(t?.input ?? 0),
    outputTokens: Number(t?.output ?? 0),
    costUsd: Number(t?.cost ?? 0),
    webhookDeliveries: Object.fromEntries(deliveries.map((d) => [d.status, d._count._all])),
  };
}
