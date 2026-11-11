/** Run 4, J4: triage and run comparison against a real Postgres. */
import { beforeEach, describe, expect, it } from "vitest";
import { db } from "@/lib/db";
import { modelPrecision, previousRun, runHistory, setTriage, triageFor } from "@/lib/triage";
import { hasTestDb } from "../test/use-test-db";

const SHOP = "https://shop.test/";

async function workspace(slug: string) {
  return db.workspace.create({ data: { name: slug, slug } });
}

async function runWithBug(workspaceId: string, fingerprint: string, createdAt: Date, fields: Record<string, unknown> = {}) {
  const run = await db.run.create({ data: { workspaceId, targetUrl: SHOP, mode: "interactive", status: "done", provider: "ollama", model: "gemma4:12b", createdAt } });
  const bug = await db.bug.create({
    data: { runId: run.id, title: "Total ignores quantity", severity: "high", category: "functional", pageUrl: `${SHOP}cart`, source: "agent", status: "confirmed", fingerprint, reproSteps: [], evidence: {}, ...fields },
  });
  return { run, bug };
}

describe.skipIf(!hasTestDb)("triage (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, runs, bugs, finding_triage, audit_log CASCADE");
  });

  it("a decision is stored per site and fingerprint, audited, and found again from a later run", async () => {
    const a = await workspace("a");
    const first = await runWithBug(a.id, "fp1", new Date("2026-11-01"));
    const saved = await setTriage(a.id, null, first.bug.id, { state: "false_positive", comment: "2 × $12 is right" });
    expect(saved).toMatchObject({ ok: true, triage: { state: "false_positive" } });
    expect(await triageFor(a.id, "https://shop.test", ["fp1"])).toMatchObject({ fp1: { state: "false_positive", comment: "2 × $12 is right" } });
    expect(await db.auditLog.count({ where: { action: "triage.changed" } })).toBe(1);

    const later = await runWithBug(a.id, "fp1", new Date("2026-11-02"));
    const previous = await previousRun(a.id, later.run);
    expect(previous?.id).toBe(first.run.id);
  });

  it("another workspace can't triage our findings", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    const { bug } = await runWithBug(a.id, "fp1", new Date());
    expect(await setTriage(b.id, null, bug.id, { state: "wont_fix" })).toMatchObject({ ok: false, status: 404 });
  });

  it("counts each model's false positives on the workspace's own sites", async () => {
    const a = await workspace("a");
    const one = await runWithBug(a.id, "fp1", new Date("2026-11-01"));
    await runWithBug(a.id, "fp2", new Date("2026-11-02"));
    await runWithBug(a.id, "fp1", new Date("2026-11-03"), { suppressed: true }); // the repeat, suppressed
    await setTriage(a.id, null, one.bug.id, { state: "false_positive" });
    expect(await modelPrecision(a.id)).toEqual([{ provider: "ollama", model: "gemma4:12b", reported: 3, falsePositives: 2, precision: 1 / 3 }]);
  });

  it("the run page's history: new, still present, fixed, triage carried over, suppressed counted", async () => {
    const a = await workspace("a");
    const first = await runWithBug(a.id, "kept", new Date("2026-11-01"));
    await db.bug.create({ data: { runId: first.run.id, title: "Old 404", severity: "low", category: "broken-link", pageUrl: SHOP, source: "deterministic", status: "confirmed", fingerprint: "gone", reproSteps: [], evidence: {} } });
    await setTriage(a.id, null, first.bug.id, { state: "wont_fix" });
    const second = await runWithBug(a.id, "kept", new Date("2026-11-02"));
    const added = await db.bug.create({ data: { runId: second.run.id, title: "New crash", severity: "high", category: "console-error", pageUrl: SHOP, source: "deterministic", status: "confirmed", fingerprint: "fresh", reproSteps: [], evidence: {} } });
    await db.bug.create({ data: { runId: second.run.id, title: "Noise", severity: "low", category: "ux", pageUrl: SHOP, source: "agent", status: "confirmed", fingerprint: "noise", suppressed: true, reproSteps: [], evidence: {} } });

    const run = await db.run.findUniqueOrThrow({ where: { id: second.run.id }, include: { bugs: true } });
    const history = await runHistory(a.id, run);
    expect(history.previousRunId).toBe(first.run.id);
    expect(history.change).toEqual({ [second.bug.id]: "still_present", [added.id]: "new" });
    expect(history.fixed).toEqual([{ title: "Old 404", severity: "low", pageUrl: SHOP }]);
    expect(history.triage.kept).toMatchObject({ state: "wont_fix" });
    expect(history.suppressed).toBe(1);
  });
});
