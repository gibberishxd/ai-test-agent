/**
 * Findings across releases (run 4, J4).
 *
 * The worker gives every finding a fingerprint (apps/worker/src/worker/fingerprint.py): the same
 * bug in a later run of the same target has the same fingerprint. Here:
 * - `compareRuns`: against the previous finished run of the target, which findings are new, still
 *   present, or fixed (reported before, not now);
 * - triage: a member marks a finding confirmed, false positive or won't fix, with a comment. The
 *   decision is stored per workspace, site and fingerprint, so it follows the finding into later
 *   runs; the worker suppresses false positives there (and they are counted per model).
 */
import { db } from "@/lib/db";

export const TRIAGE_STATES = ["confirmed", "false_positive", "wont_fix"] as const;
export type TriageState = (typeof TRIAGE_STATES)[number];
const MAX_COMMENT = 500;

type Finding = { fingerprint: string | null; status: string; suppressed: boolean };

/** What a run reports: not dismissed by verification, not suppressed by triage. */
export function reportedBugs<T extends Finding>(bugs: T[]): T[] {
  return bugs.filter((bug) => bug.status !== "dismissed" && !bug.suppressed);
}

export type Comparison<T> = { new: T[]; stillPresent: T[]; fixed: T[] };

/** `previous`: the bugs of the target's previous finished run, or null if there is none. */
export function compareRuns<T extends Finding>(previous: T[] | null, current: T[]): Comparison<T> {
  const now = reportedBugs(current);
  if (previous === null) return { new: now, stillPresent: [], fixed: [] };
  const before = reportedBugs(previous);
  const beforeKeys = new Set(before.map((b) => b.fingerprint).filter(Boolean));
  const nowKeys = new Set(now.map((b) => b.fingerprint).filter(Boolean));
  return {
    new: now.filter((b) => !b.fingerprint || !beforeKeys.has(b.fingerprint)),
    stillPresent: now.filter((b) => b.fingerprint && beforeKeys.has(b.fingerprint)),
    fixed: before.filter((b) => b.fingerprint && !nowKeys.has(b.fingerprint)),
  };
}

export function parseTriageInput(body: Record<string, unknown>): { ok: true; value: { state: TriageState; comment: string | null } } | { ok: false; error: string } {
  const state = body.state as TriageState;
  if (!TRIAGE_STATES.includes(state)) return { ok: false, error: "Choose confirmed, false positive or won't fix." };
  const comment = typeof body.comment === "string" ? body.comment.trim().slice(0, MAX_COMMENT) || null : null;
  return { ok: true, value: { state, comment } };
}

export function originOf(url: string): string {
  return new URL(url).origin;
}

/** The target's previous finished run in this workspace (null for its first run). */
export async function previousRun(workspaceId: string, run: { id: string; targetUrl: string; createdAt: Date }) {
  return db.run.findFirst({
    where: { workspaceId, targetUrl: run.targetUrl, status: "done", createdAt: { lt: run.createdAt }, NOT: { id: run.id } },
    orderBy: { createdAt: "desc" },
    include: { bugs: true },
  });
}

export type TriageView = { state: TriageState; comment: string | null; updatedAt: string };

/** The workspace's decisions for these fingerprints on this site. */
export async function triageFor(workspaceId: string, origin: string, fingerprints: string[]): Promise<Record<string, TriageView>> {
  if (fingerprints.length === 0) return {};
  const rows = await db.findingTriage.findMany({ where: { workspaceId, origin, fingerprint: { in: fingerprints } } });
  return Object.fromEntries(
    rows.map((row) => [row.fingerprint, { state: row.state as TriageState, comment: row.comment, updatedAt: row.updatedAt.toISOString() }]),
  );
}

/** Record a decision on a finding (by its fingerprint) for this workspace and site. */
export async function setTriage(workspaceId: string, userId: string | null, bugId: string, body: Record<string, unknown>) {
  const parsed = parseTriageInput(body);
  if (!parsed.ok) return { ok: false as const, status: 400, error: parsed.error };
  const bug = await db.bug.findFirst({ where: { id: bugId, run: { workspaceId } }, include: { run: true } });
  if (!bug) return { ok: false as const, status: 404, error: "Finding not found." };
  if (!bug.fingerprint) return { ok: false as const, status: 409, error: "This finding is from before fingerprints and can't be triaged." };
  const origin = originOf(bug.run.targetUrl);
  const { state, comment } = parsed.value;
  const row = await db.findingTriage.upsert({
    where: { workspaceId_origin_fingerprint: { workspaceId, origin, fingerprint: bug.fingerprint } },
    create: { workspaceId, origin, fingerprint: bug.fingerprint, state, comment, title: bug.title, updatedById: userId },
    update: { state, comment, title: bug.title, updatedById: userId },
  });
  await db.auditLog.create({
    data: { workspaceId, userId, action: "triage.changed", runId: bug.runId, metadata: { fingerprint: bug.fingerprint, state, title: bug.title } },
  });
  return { ok: true as const, triage: { state: row.state as TriageState, comment: row.comment, updatedAt: row.updatedAt.toISOString() } };
}

export type ModelPrecision = { provider: string; model: string; reported: number; falsePositives: number; precision: number | null };

/**
 * How often each model was wrong on this workspace's own sites: agent findings it reported, and how
 * many of those the workspace marked false positive (including later suppressed repeats).
 */
export async function modelPrecision(workspaceId: string): Promise<ModelPrecision[]> {
  const rows = await db.$queryRaw<{ provider: string; model: string; reported: bigint; false_positives: bigint }[]>`
    SELECT r.provider, r.model,
           count(*) AS reported,
           count(*) FILTER (WHERE t.state = 'false_positive') AS false_positives
    FROM bugs b
    JOIN runs r ON r.id = b.run_id
    LEFT JOIN finding_triage t
      ON t.workspace_id = r.workspace_id AND t.fingerprint = b.fingerprint
     AND t.origin = substring(r.target_url from '^[a-z]+://[^/]+')
    WHERE r.workspace_id = ${workspaceId}::uuid AND b.source = 'agent' AND b.status <> 'dismissed'
      AND r.provider IS NOT NULL
    GROUP BY r.provider, r.model
    ORDER BY r.provider, r.model`;
  return rows.map((row) => {
    const reported = Number(row.reported);
    const falsePositives = Number(row.false_positives);
    return { provider: row.provider, model: row.model, reported, falsePositives, precision: reported ? (reported - falsePositives) / reported : null };
  });
}

export type RunHistory = {
  previousRunId: string | null;
  /** bug id → whether the previous run of the target reported it too */
  change: Record<string, "new" | "still_present">;
  fixed: { title: string; severity: string; pageUrl: string }[];
  triage: Record<string, TriageView>;
  suppressed: number;
};

/** What the run page shows about this run's findings compared with the target's last run. */
export async function runHistory(
  workspaceId: string,
  run: { id: string; targetUrl: string; createdAt: Date; status: string; bugs: (Finding & { id: string; title: string; severity: string; pageUrl: string })[] },
): Promise<RunHistory> {
  const previous = await previousRun(workspaceId, run);
  const comparison = compareRuns(previous?.bugs ?? null, run.bugs);
  const fingerprints = run.bugs.map((b) => b.fingerprint).filter((f): f is string => Boolean(f));
  return {
    previousRunId: previous?.id ?? null,
    change: Object.fromEntries([
      ...comparison.new.map((b) => [b.id, "new"] as const),
      ...comparison.stillPresent.map((b) => [b.id, "still_present"] as const),
    ]),
    // A run still in progress hasn't had the chance to find everything: nothing is "fixed" yet.
    fixed: run.status === "done" ? comparison.fixed.map((b) => ({ title: b.title, severity: b.severity, pageUrl: b.pageUrl })) : [],
    triage: await triageFor(workspaceId, originOf(run.targetUrl), fingerprints),
    suppressed: run.bugs.filter((b) => b.suppressed).length,
  };
}
