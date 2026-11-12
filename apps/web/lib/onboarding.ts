/**
 * Getting started (run 5, K5): what a new team does on the way to its first report, and how
 * far it is. Shown on the dashboard until the first report exists.
 */
import { tenantDb } from "@/lib/tenant-db";

export type OnboardingState = {
  verifiedDomains: number;
  /** Workspace models that passed Test connection. */
  usableModels: number;
  runs: number;
  /** The first run that finished: its report is the goal of the whole path. */
  finishedRunId: string | null;
};

export type OnboardingStep = {
  key: "workspace" | "target" | "model" | "run" | "report";
  title: string;
  detail: string;
  done: boolean;
  href?: string;
};

export function onboardingSteps(state: OnboardingState): OnboardingStep[] {
  const started = state.runs > 0;
  return [
    { key: "workspace", title: "Your workspace", detail: "Created when you signed up. Invite your team in Settings → Members.", done: true },
    {
      key: "target",
      title: "Choose what to test",
      detail: "Verify your site's domain (a DNS record or a file) to let the agent click around it, or start with the demo shop.",
      done: state.verifiedDomains > 0 || started,
      href: "/settings#domains",
    },
    {
      key: "model",
      title: "Pick a model",
      detail: "Runs use the server's model unless you add your own (any provider) in Settings → Models.",
      done: state.usableModels > 0 || started,
      href: "/settings#models",
    },
    { key: "run", title: "Start a run", detail: "Paste the URL below and press Start test. You can watch the agent's screen live.", done: started },
    {
      key: "report",
      title: "Read the report",
      detail: "Every finding comes with steps, evidence and a screenshot, checked by a replay.",
      done: state.finishedRunId !== null,
      href: state.finishedRunId ? `/runs/${state.finishedRunId}` : undefined,
    },
  ];
}

export async function onboardingState(workspaceId: string): Promise<OnboardingState> {
  const db = tenantDb(workspaceId);
  const [verifiedDomains, models, runs, finished] = await Promise.all([
    db.domain.count({ where: { workspaceId, verifiedAt: { not: null } } }),
    db.modelConfig.findMany({ where: { workspaceId }, select: { probe: true } }),
    db.run.count({ where: { workspaceId } }),
    db.run.findFirst({ where: { workspaceId, status: "done" }, orderBy: { finishedAt: "asc" }, select: { id: true } }),
  ]);
  const usableModels = models.filter((m) => (m.probe as { ok?: boolean } | null)?.ok === true).length;
  return { verifiedDomains, usableModels, runs, finishedRunId: finished?.id ?? null };
}
