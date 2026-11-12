/**
 * Prometheus metrics (run 4, J6), computed from the database: with several web servers and
 * workers, every server reports the same totals, and nothing is lost when a process restarts.
 */
import { serviceMetrics } from "@/lib/system-db";

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

/**
 * Totals across every workspace, from one database function (service_metrics): the web role
 * can't read other workspaces' rows, but the operator's dashboard needs counts and sums.
 */
export async function readMetrics(): Promise<MetricValues> {
  const rows = await serviceMetrics();
  const by = (metric: string) => Object.fromEntries(rows.filter((r) => r.metric === metric).map((r) => [r.label, Number(r.value)]));
  const total = (metric: string) => Number(rows.find((r) => r.metric === metric)?.value ?? 0);
  const runsByStatus = by("runs");
  return {
    runsByStatus,
    queueDepth: runsByStatus.queued ?? 0,
    runSecondsSum: total("run_seconds_sum"),
    runSecondsCount: total("runs_finished"),
    inputTokens: total("input_tokens"),
    outputTokens: total("output_tokens"),
    costUsd: total("cost_usd"),
    webhookDeliveries: by("webhook_deliveries"),
  };
}
