import { describe, expect, it } from "vitest";
import { formatMetrics } from "./metrics";

describe("formatMetrics", () => {
  it("renders the Prometheus text format with help, type and labels", () => {
    const text = formatMetrics({
      runsByStatus: { queued: 2, running: 1, done: 40, failed: 3, stopped: 1 },
      queueDepth: 2,
      runSecondsSum: 1200.5,
      runSecondsCount: 4,
      inputTokens: 123456,
      outputTokens: 789,
      costUsd: 1.25,
      webhookDeliveries: { delivered: 9, pending: 1, failed: 0 },
    });
    expect(text).toContain("# TYPE ata_runs_total counter");
    expect(text).toContain('ata_runs_total{status="failed"} 3');
    expect(text).toContain("# TYPE ata_queue_depth gauge\nata_queue_depth 2");
    expect(text).toContain("ata_run_duration_seconds_sum 1200.5\nata_run_duration_seconds_count 4");
    expect(text).toContain('ata_model_tokens_total{direction="input"} 123456');
    expect(text).toContain("ata_model_cost_usd_total 1.25");
    expect(text).toContain('ata_webhook_deliveries{status="pending"} 1');
    expect(text.endsWith("\n")).toBe(true);
  });
});
