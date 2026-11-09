/**
 * The JSON the browser gets for a run: what the live page polls and the "Download JSON" file.
 * Dates become ISO strings; only fields the UI needs are included.
 */
import type { RunDetail } from "@/lib/runs";

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
  error: string | null;
  summary: Record<string, unknown> | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  steps: StepView[];
  bugs: BugView[];
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
    error: run.error,
    summary: (run.summary as Record<string, unknown> | null) ?? null,
    createdAt: run.createdAt.toISOString(),
    startedAt: iso(run.startedAt),
    finishedAt: iso(run.finishedAt),
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
    })),
  };
}
