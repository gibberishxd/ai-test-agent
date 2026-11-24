/**
 * Deep mode in the web app (run 9), against a real Postgres: starting a deep run, its limits,
 * stopping and resuming a paused run.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { adminDb as db } from "../test/admin-db";
import { deepLimits, requestResume, saveDeepLimits } from "@/lib/deep";
import { requestStop, startRun } from "@/lib/runs";
import type { RequestContext } from "@/lib/workspace";
import { hasTestDb } from "../test/use-test-db";

const DEMO = "http://localhost:5173/";

function member(workspaceId: string): RequestContext {
  return { workspaceId, userId: null, signedIn: true, role: "member" };
}

describe.skipIf(!hasTestDb)("deep mode (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, users, runs, steps, bugs, audit_log, domains CASCADE");
  });

  it("starts an interactive run with the deep engine and its model", async () => {
    const ws = await db.workspace.create({ data: { name: "d", slug: "d" } });
    const started = await startRun(member(ws.id), { targetUrl: DEMO, mode: "deep", engineModel: "claude-opus-5-5" }, "1.2.3.4");
    expect(started.ok).toBe(true);
    const run = await db.run.findFirstOrThrow({ where: { workspaceId: ws.id } });
    expect([run.mode, run.engine, run.engineModel]).toEqual(["interactive", "deep", "claude-opus-5-5"]);
    // The plan's per-run step limit is the current loop's; a deep run keeps its own limits.
    expect(run.maxSteps).toBeNull();
  });

  it("keeps the plan's step limit on current-loop runs", async () => {
    const ws = await db.workspace.create({ data: { name: "l", slug: "l" } });
    await startRun(member(ws.id), { targetUrl: DEMO, mode: "interactive" }, "1.2.3.4");
    const run = await db.run.findFirstOrThrow({ where: { workspaceId: ws.id } });
    expect(run.engine).toBe("loop");
    expect(run.maxSteps).not.toBeNull();
  });

  it("resumes only a paused run, and clears why it paused", async () => {
    const ws = await db.workspace.create({ data: { name: "r", slug: "r" } });
    const paused = await db.run.create({
      data: { workspaceId: ws.id, targetUrl: DEMO, mode: "interactive", engine: "deep", status: "paused", pausedReason: "usage limit" },
    });
    const done = await db.run.create({ data: { workspaceId: ws.id, targetUrl: DEMO, status: "done" } });
    expect(await requestResume(ws.id, paused.id)).toBe(true);
    expect(await db.run.findUniqueOrThrow({ where: { id: paused.id } })).toMatchObject({ status: "queued", pausedReason: null });
    expect(await requestResume(ws.id, done.id)).toBe(false);
  });

  it("stopping a paused run gives it up", async () => {
    const ws = await db.workspace.create({ data: { name: "s", slug: "s" } });
    const run = await db.run.create({
      data: { workspaceId: ws.id, targetUrl: DEMO, mode: "interactive", engine: "deep", status: "paused" },
    });
    expect(await requestStop(ws.id, run.id)).toBe(true);
    expect((await db.run.findUniqueOrThrow({ where: { id: run.id } })).status).toBe("stopped");
  });

  it("saves the workspace's limits, minutes as seconds", async () => {
    const ws = await db.workspace.create({ data: { name: "w", slug: "w" } });
    await saveDeepLimits(ws.id, null, { steps: 800, minutes: 90 });
    expect(await db.workspace.findUniqueOrThrow({ where: { id: ws.id } })).toMatchObject({ deepMaxSteps: 800, deepMaxSeconds: 5400 });
    expect(await deepLimits(ws.id)).toEqual({ steps: 800, minutes: 90 });
    await saveDeepLimits(ws.id, null, { steps: null, minutes: null });
    expect(await deepLimits(ws.id)).toEqual({ steps: null, minutes: null });
  });
});
