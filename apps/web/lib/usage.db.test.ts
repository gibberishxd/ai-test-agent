/**
 * Usage you could bill for (run 5, K4): the workspace's plan, this month's runs and cost per
 * model (explorer and reviewer apart), seats; the admin view across workspaces; and the plan's
 * limits applied when a run starts.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { adminDb as db } from "../test/admin-db";
import { startRun } from "@/lib/runs";
import { platformUsage, workspaceUsage } from "@/lib/usage";
import { hasTestDb } from "../test/use-test-db";

const DEMO = "http://localhost:5173/";

async function workspace(slug: string, planId = "free") {
  return db.workspace.create({ data: { name: slug, slug, planId } });
}

/** A run that finished: the database records its usage event when the status turns final. */
async function finishedRun(workspaceId: string, fields: Record<string, unknown>) {
  const run = await db.run.create({ data: { workspaceId, targetUrl: DEMO, mode: "interactive", status: "running", startedAt: new Date(), ...fields } });
  return db.run.update({ where: { id: run.id }, data: { status: "done", finishedAt: new Date() } });
}

describe.skipIf(!hasTestDb)("usage and plans (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, users, runs, usage_events, audit_log CASCADE");
  });

  it("a workspace's usage this month: plan limits, runs, cost per model, explorer and reviewer apart", async () => {
    const ws = await workspace("acme", "team");
    await db.user.create({ data: { email: "a@example.com", workspaceId: ws.id, role: "owner" } });
    await finishedRun(ws.id, { provider: "ollama", model: "gemma4:12b", inputTokens: 1000, outputTokens: 100, costUsd: 0.2, reviewerProvider: "claude", reviewerModel: "claude-sonnet-5-5", reviewerInputTokens: 400, reviewerOutputTokens: 40, reviewerCostUsd: 0.2 });
    await finishedRun(ws.id, { provider: "ollama", model: "gemma4:12b", inputTokens: 500, outputTokens: 50, costUsd: 0 });

    const usage = await workspaceUsage(ws.id);
    expect(usage.plan).toMatchObject({ id: "team", runsPerMonth: 300, maxStepsPerRun: 80, seats: 10, allowedProviders: [] });
    expect(usage.runs).toBe(2);
    expect(usage.seatsUsed).toBe(1);
    expect(usage.costUsd).toBeCloseTo(0.2);
    expect(usage.byModel).toEqual([
      { role: "explorer", provider: "ollama", model: "gemma4:12b", runs: 2, inputTokens: 1100, outputTokens: 110, costUsd: 0 },
      { role: "reviewer", provider: "claude", model: "claude-sonnet-5-5", runs: 1, inputTokens: 400, outputTokens: 40, costUsd: 0.2 },
    ]);
  });

  it("another workspace's usage never shows", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    await finishedRun(b.id, { provider: "ollama", model: "m", costUsd: 0 });
    expect((await workspaceUsage(a.id)).runs).toBe(0);
  });

  it("the admin view is for platform admins only", async () => {
    const ws = await workspace("ops");
    const admin = await db.user.create({ data: { email: "ops@example.com", workspaceId: ws.id, role: "owner", isPlatformAdmin: true } });
    const member = await db.user.create({ data: { email: "m@example.com", workspaceId: ws.id, role: "member" } });
    await finishedRun(ws.id, { provider: "ollama", model: "m", costUsd: 0 });
    expect(await platformUsage(member.id)).toBeNull();
    const rows = await platformUsage(admin.id);
    expect(rows?.find((r) => r.slug === "ops")).toMatchObject({ planId: "free", runs: 1, members: 2 });
  });

  it("starting a run follows the plan: allowed models and the steps a run may take", async () => {
    const ws = await workspace("free-ws", "free");
    const model = await db.modelConfig.create({ data: { workspaceId: ws.id, label: "Claude", provider: "claude", model: "claude-sonnet-5-5", probe: { ok: true } } });
    const context = { workspaceId: ws.id, userId: null, signedIn: true, role: "member" as const };

    const refused = await startRun(context, { targetUrl: DEMO, mode: "passive", modelConfigId: model.id }, "1.2.3.4");
    expect(refused).toMatchObject({ ok: false, status: 403 });
    expect(JSON.stringify(refused)).toContain("Free plan doesn't include claude");

    const started = await startRun(context, { targetUrl: DEMO, mode: "passive" }, "1.2.3.4", { maxSteps: 400 });
    if (!started.ok) throw new Error(JSON.stringify(started));
    expect((await db.run.findUniqueOrThrow({ where: { id: started.id } })).maxSteps).toBe(40); // the plan's cap
  });
});
