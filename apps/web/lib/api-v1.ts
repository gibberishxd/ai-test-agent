/**
 * The public API, version 1 (run 4, J3): what CI pipelines call. docs/API.md shows examples;
 * openapi.json is the contract and tests check the routes against it.
 *
 * Every request carries `Authorization: Bearer ata_…` (a workspace API key) and is rate-limited
 * per key. Starting a run goes through the same `startRun` as the dashboard, so the monthly
 * quota, domain verification and model checks are exactly the same.
 */
import { authenticateApiKey, rateLimit, type ApiCaller } from "@/lib/api-keys";

export const MAX_API_STEPS = 100;
export const MAX_API_MINUTES = 60;

type RunBody = { targetUrl: unknown; mode: unknown; focus: unknown; modelConfigId: unknown };
export type ApiRunInput = { body: RunBody; maxSteps: number | null; maxSeconds: number | null };
export type ApiErrors = Partial<Record<"target_url" | "mode" | "focus" | "model_id" | "max_steps" | "max_minutes", string>>;

function wholeNumber(value: unknown, min: number, max: number): number | null | undefined {
  if (value === undefined || value === null) return null;
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max ? value : undefined;
}

export function parseApiRunInput(raw: Record<string, unknown>): { ok: true; value: ApiRunInput } | { ok: false; errors: ApiErrors } {
  const errors: ApiErrors = {};
  if (typeof raw.target_url !== "string") errors.target_url = "target_url is required: the URL to test.";
  if (raw.mode !== undefined && raw.mode !== "passive" && raw.mode !== "interactive") errors.mode = 'mode is "passive" or "interactive".';
  if (raw.focus !== undefined && raw.focus !== null && typeof raw.focus !== "string") errors.focus = "focus is a string.";
  if (raw.model_id !== undefined && raw.model_id !== null && typeof raw.model_id !== "string") errors.model_id = "model_id is a model's id (Settings → Models).";
  const maxSteps = wholeNumber(raw.max_steps, 1, MAX_API_STEPS);
  if (maxSteps === undefined) errors.max_steps = `max_steps is a whole number from 1 to ${MAX_API_STEPS}.`;
  const maxMinutes = wholeNumber(raw.max_minutes, 1, MAX_API_MINUTES);
  if (maxMinutes === undefined) errors.max_minutes = `max_minutes is a whole number from 1 to ${MAX_API_MINUTES}.`;
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    value: {
      body: { targetUrl: raw.target_url, mode: raw.mode ?? "passive", focus: raw.focus ?? null, modelConfigId: raw.model_id ?? null },
      maxSteps: maxSteps ?? null,
      maxSeconds: maxMinutes ? maxMinutes * 60 : null,
    },
  };
}

/** Field names the dashboard's validation uses → the API's names, for error messages. */
export function apiErrorNames(errors: Record<string, string | undefined>): Record<string, string> {
  const names: Record<string, string> = { targetUrl: "target_url", mode: "mode", focus: "focus", model: "model_id" };
  return Object.fromEntries(Object.entries(errors).filter(([, v]) => v).map(([k, v]) => [names[k] ?? k, v as string]));
}

type ApiBug = {
  id: string;
  title: string;
  severity: string;
  category: string;
  pageUrl: string;
  status: string;
  source: string;
  expected: string | null;
  actual: string | null;
  reproSteps: unknown; // a JSON column: a list of strings
  suppressed?: boolean; // triaged as a false positive earlier (run 4, J4)
};
type ApiRun = {
  id: string;
  targetUrl: string;
  mode: string;
  status: string;
  costUsd: number;
  pagesVisited: number;
  createdAt: Date;
  startedAt: Date | null;
  finishedAt: Date | null;
  bugs: ApiBug[];
};

export const SEVERITIES = ["critical", "high", "medium", "low"] as const;
export const FINAL_STATUSES = ["done", "failed", "stopped"];

const steps = (value: unknown): string[] => (Array.isArray(value) ? value.map(String) : []);

/** What a run reports to its user: every bug that verification didn't dismiss. */
function reported(run: ApiRun): ApiBug[] {
  return run.bugs.filter((bug) => bug.status !== "dismissed" && !bug.suppressed);
}

export function apiStatus(run: ApiRun, baseUrl: string) {
  const counts = Object.fromEntries(SEVERITIES.map((s) => [s, reported(run).filter((b) => b.severity === s).length]));
  return {
    id: run.id,
    status: run.status,
    finished: FINAL_STATUSES.includes(run.status),
    target_url: run.targetUrl,
    mode: run.mode,
    created_at: run.createdAt.toISOString(),
    started_at: run.startedAt?.toISOString() ?? null,
    finished_at: run.finishedAt?.toISOString() ?? null,
    duration_s: run.startedAt && run.finishedAt ? Math.round((+run.finishedAt - +run.startedAt) / 1000) : null,
    pages_visited: run.pagesVisited,
    cost_usd: run.costUsd,
    counts,
    links: {
      self: `${baseUrl}/api/v1/runs/${run.id}`,
      report: `${baseUrl}/api/v1/runs/${run.id}/report`,
      junit: `${baseUrl}/api/v1/runs/${run.id}/report?format=junit`,
      dashboard: `${baseUrl}/runs/${run.id}`,
    },
  };
}

export function apiReport(run: ApiRun, baseUrl = "") {
  const status = apiStatus(run, baseUrl);
  return {
    run: status,
    counts: status.counts,
    bugs: reported(run).map((bug) => ({
      id: bug.id,
      title: bug.title,
      severity: bug.severity,
      category: bug.category,
      page_url: bug.pageUrl,
      status: bug.status,
      source: bug.source,
      expected: bug.expected,
      actual: bug.actual,
      repro_steps: steps(bug.reproSteps),
    })),
  };
}

const escapeXml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");

/**
 * JUnit XML, which every CI system can display: one failing test case per reported bug (its
 * severity as the failure type), or one passing case when nothing was found.
 */
export function junitReport(run: ApiRun): string {
  const bugs = reported(run);
  const seconds = run.startedAt && run.finishedAt ? (+run.finishedAt - +run.startedAt) / 1000 : 0;
  const suite = escapeXml(`AI Test Agent: ${run.targetUrl}`);
  const cases = bugs.length
    ? bugs.map((bug) => {
        const body = [
          `Page: ${bug.pageUrl}`,
          `Expected: ${bug.expected ?? "-"}`,
          `Actual: ${bug.actual ?? "-"}`,
          "Steps:",
          ...steps(bug.reproSteps).map((step, i) => `  ${i + 1}. ${step}`),
        ].join("\n");
        return (
          `    <testcase name="${escapeXml(bug.title)}" classname="${escapeXml(bug.category)}">\n` +
          `      <failure type="${escapeXml(bug.severity)}" message="${escapeXml(bug.title)}">${escapeXml(body)}</failure>\n` +
          `    </testcase>`
        );
      })
    : [`    <testcase name="No bugs found" classname="run"></testcase>`];
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<testsuites name="AI Test Agent" tests="${cases.length}" failures="${bugs.length}" time="${seconds.toFixed(1)}">`,
    `  <testsuite name="${suite}" tests="${cases.length}" failures="${bugs.length}" time="${seconds.toFixed(1)}" timestamp="${run.createdAt.toISOString()}">`,
    ...cases,
    "  </testsuite>",
    "</testsuites>",
    "",
  ].join("\n");
}

/** Authenticate and rate-limit an API request; `handle` runs only for a valid, allowed key. */
export async function withApiKey(request: Request, handle: (caller: ApiCaller) => Promise<Response>): Promise<Response> {
  const caller = await authenticateApiKey(request.headers);
  if (!caller) {
    return Response.json(
      { error: "A valid API key is required: Authorization: Bearer ata_… (Settings → API keys)." },
      { status: 401, headers: { "WWW-Authenticate": "Bearer" } },
    );
  }
  const limited = await rateLimit(caller);
  if (!limited.ok) {
    return Response.json(
      { error: "Too many requests for this API key. Slow down and retry." },
      { status: 429, headers: { "Retry-After": String(limited.retryAfterS) } },
    );
  }
  return handle(caller);
}

/** The app's public base URL, for links in responses. */
export function baseUrlOf(request: Request): string {
  return process.env.PUBLIC_BASE_URL?.replace(/\/$/, "") || new URL(request.url).origin;
}
