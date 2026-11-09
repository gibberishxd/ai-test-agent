/**
 * TypeScript copy of the JSON shapes the worker writes (Pydantic models in
 * apps/worker/src/worker/report.py). `schema.json` is exported from those models;
 * contracts.test.ts fails if these types and the schema drift apart.
 */

export type Severity = "critical" | "high" | "medium" | "low";
export type BugSource = "deterministic" | "agent";
export type BugStatus = "candidate" | "confirmed" | "dismissed";

export type BugReport = {
  title: string;
  severity: Severity;
  category: string;
  page_url: string;
  expected: string | null;
  actual: string | null;
  repro_steps: string[];
  evidence: Record<string, unknown>;
  reasoning: string | null;
  screenshot: string | null;
  step_indexes: number[];
  source: BugSource;
  status: BugStatus;
  dismiss_reason: string | null;
};

/**
 * Every BugReport field and whether the worker always sends it. `satisfies` makes the
 * compiler check this object lists exactly the keys of BugReport.
 */
export const BUG_REPORT_FIELDS = {
  title: "required",
  severity: "required",
  category: "required",
  page_url: "required",
  expected: "optional",
  actual: "optional",
  repro_steps: "optional",
  evidence: "optional",
  reasoning: "optional",
  screenshot: "optional",
  step_indexes: "optional",
  source: "required",
  status: "optional",
  dismiss_reason: "optional",
} as const satisfies Record<keyof BugReport, "required" | "optional">;

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
