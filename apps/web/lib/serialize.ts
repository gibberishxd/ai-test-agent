/**
 * The JSON the browser gets for a run: what the live page polls and the "Download JSON" file.
 * Dates become ISO strings; only fields the UI needs are included.
 */
import type { RunDetail } from "@/lib/runs";
import type { RunHistory } from "@/lib/triage";

export type StepView = {
  index: number;
  action: string;
  args: Record<string, unknown>;
  reasoning: string | null;
  url: string | null;
  screenshot: string | null;
  events: { type: string; text: string }[];
  blocked: boolean;
  blockReason: string | null;
  costUsd: number;
  /** Run 6: the model the provider reported, and the API-equivalent cost (an estimate for claude-cli). */
  model: string | null;
  estimatedCostUsd: number;
  createdAt: string;
};

export type BugView = {
  id: string;
  title: string;
  severity: string;
  category: string;
  pageUrl: string;
  expected: string | null;
  actual: string | null;
  reproSteps: string[];
  evidence: Record<string, unknown>;
  reasoning: string | null;
  screenshot: string | null;
  source: string;
  status: string;
  dismissReason: string | null;
  /** Run 4, J4: the same bug in later runs has the same fingerprint. */
  fingerprint: string | null;
  /** Hidden: the workspace triaged this fingerprint as a false positive. */
  suppressed: boolean;
};

export type FlowResultView = {
  name: string;
  /** passed | replayed | repaired | failed | skipped */
  status: string;
  /** Checked by replaying its saved script, with no model call. */
  replayed: boolean;
  modelCalls: number;
  estimatedCostUsd: number;
  detail: string | null;
};

export type RunView = {
  id: string;
  targetUrl: string;
  mode: string;
  focus: string | null;
  status: string;
  stopRequested: boolean;
  provider: string | null;
  model: string | null;
  pagesVisited: number;
  stepCount: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  /** Run 6: the cached share of inputTokens and the API-equivalent cost (an estimate for claude-cli). */
  cacheReadTokens: number;
  cacheWriteTokens: number;
  estimatedCostUsd: number;
  error: string | null;
  summary: Record<string, unknown> | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  steps: StepView[];
  bugs: BugView[];
  /** Run 7, M4: each critical flow's result in this run (empty when the target has none). */
  flows: FlowResultView[];
  /** Compared with the target's previous run, and the workspace's triage (members only). */
  history?: RunHistory | null;
};

const iso = (date: Date | null) => (date ? date.toISOString() : null);

export function serializeRun(run: RunDetail): RunView {
  return {
    id: run.id,
    targetUrl: run.targetUrl,
    mode: run.mode,
    focus: run.focus,
    status: run.status,
    stopRequested: run.stopRequested,
    provider: run.provider,
    model: run.model,
    pagesVisited: run.pagesVisited,
    stepCount: run.stepCount,
    inputTokens: run.inputTokens,
    outputTokens: run.outputTokens,
    costUsd: run.costUsd,
    cacheReadTokens: run.cacheReadTokens,
    cacheWriteTokens: run.cacheWriteTokens,
    estimatedCostUsd: run.estimatedCostUsd,
    error: run.error,
    summary: (run.summary as Record<string, unknown> | null) ?? null,
    createdAt: run.createdAt.toISOString(),
    startedAt: iso(run.startedAt),
    finishedAt: iso(run.finishedAt),
    flows: (run.flowResults ?? []).map((r) => ({
      name: r.flow.name,
      status: r.status,
      replayed: r.replayed,
      modelCalls: r.modelCalls,
      estimatedCostUsd: r.estimatedCostUsd,
      detail: r.detail,
    })),
    steps: run.steps.map((step) => ({
      index: step.index,
      action: step.action,
      args: (step.args as Record<string, unknown>) ?? {},
      reasoning: step.reasoning,
      url: step.url,
      screenshot: step.screenshot,
      events: (step.events as { type: string; text: string }[]) ?? [],
      blocked: step.blocked,
      blockReason: step.blockReason,
      costUsd: step.costUsd,
      model: step.model,
      estimatedCostUsd: step.estimatedCostUsd,
      createdAt: step.createdAt.toISOString(),
    })),
    bugs: run.bugs.map((bug) => ({
      id: bug.id,
      title: bug.title,
      severity: bug.severity,
      category: bug.category,
      pageUrl: bug.pageUrl,
      expected: bug.expected,
      actual: bug.actual,
      reproSteps: (bug.reproSteps as string[]) ?? [],
      evidence: (bug.evidence as Record<string, unknown>) ?? {},
      reasoning: bug.reasoning,
      screenshot: bug.screenshot,
      source: bug.source,
      status: bug.status,
      dismissReason: bug.dismissReason,
      fingerprint: bug.fingerprint,
      suppressed: bug.suppressed,
    })),
  };
}
