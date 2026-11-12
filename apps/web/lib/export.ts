/**
 * Turn a bug into text a team pastes into its tracker: a GitHub issue (Markdown) or a Jira
 * description (Jira wiki markup). Pure functions, so they're easy to test.
 */

export type ExportableBug = {
  title: string;
  severity: string;
  category: string;
  pageUrl: string;
  expected: string | null;
  actual: string | null;
  reproSteps: string[];
  evidence: Record<string, unknown>;
};

export type ExportContext = { runUrl: string; targetUrl: string };

type ConsoleEvidence = { kind: string; text: string };
type RequestEvidence = { method: string; url: string; status: number | null; failure: string | null };
type A11yEvidence = { rule_id: string; targets: string[] };

/** The hard evidence, one line per item. */
export function evidenceLines(evidence: Record<string, unknown>): string[] {
  const lines: string[] = [];
  for (const error of (evidence.console_errors as ConsoleEvidence[] | undefined) ?? []) {
    lines.push(`${error.kind}: ${error.text}`);
  }
  for (const request of (evidence.failed_requests as RequestEvidence[] | undefined) ?? []) {
    lines.push(`${request.method} ${request.url} → ${request.status ?? request.failure}`);
  }
  for (const violation of (evidence.a11y as A11yEvidence[] | undefined) ?? []) {
    lines.push(`axe ${violation.rule_id}: ${violation.targets.slice(0, 5).join(", ")}`);
  }
  if (typeof evidence.link === "string") lines.push(`broken link: ${evidence.link}`);
  if (typeof evidence.observed === "string" && evidence.observed) lines.push(evidence.observed);
  const diff = evidence.replay_diff as { summary?: unknown } | undefined;
  if (diff && typeof diff.summary === "string" && diff.summary) {
    lines.push("Replay measured the last action:", ...diff.summary.split("\n"));
  }
  return lines;
}

export function toGitHubIssue(bug: ExportableBug, context: ExportContext): string {
  const steps = bug.reproSteps.map((step, i) => `${i + 1}. ${step}`).join("\n");
  const evidence = evidenceLines(bug.evidence);
  return [
    `## ${bug.title}`,
    "",
    `**Severity:** ${bug.severity} · **Category:** ${bug.category} · **Page:** ${bug.pageUrl}`,
    "",
    "### Steps to reproduce",
    steps || "1. Open the page above",
    "",
    "### Expected",
    bug.expected || "—",
    "",
    "### Actual",
    bug.actual || "—",
    ...(evidence.length ? ["", "### Evidence", "```", ...evidence, "```"] : []),
    "",
    `_Found by AI Test Agent on ${context.targetUrl} · [full report](${context.runUrl})_`,
  ].join("\n");
}

export function toJira(bug: ExportableBug, context: ExportContext): string {
  const steps = bug.reproSteps.map((step) => `# ${step}`).join("\n");
  const evidence = evidenceLines(bug.evidence);
  return [
    `h3. ${bug.title}`,
    "",
    `*Severity:* ${bug.severity} | *Category:* ${bug.category} | *Page:* ${bug.pageUrl}`,
    "",
    "h4. Steps to reproduce",
    steps || "# Open the page above",
    "",
    "h4. Expected",
    bug.expected || "-",
    "",
    "h4. Actual",
    bug.actual || "-",
    ...(evidence.length ? ["", "h4. Evidence", "{noformat}", ...evidence, "{noformat}"] : []),
    "",
    `_Found by AI Test Agent on ${context.targetUrl}_ · [Full report|${context.runUrl}]`,
  ].join("\n");
}
