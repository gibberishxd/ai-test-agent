/**
 * Row-level security (run 4, J5): even a query that forgets "WHERE workspace_id = …" can't read
 * or write another workspace's rows, because the database filters them for app_tenant.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { adminDb as db } from "../test/admin-db";
import { db as appDb } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
import { hasTestDb } from "../test/use-test-db";

async function workspaceWithRun(slug: string) {
  const workspace = await db.workspace.create({ data: { name: slug, slug } });
  const run = await db.run.create({ data: { workspaceId: workspace.id, targetUrl: `https://${slug}.test/`, mode: "passive", status: "done" } });
  await db.step.create({ data: { runId: run.id, index: 0, action: "visit", args: {}, url: run.targetUrl } });
  await db.bug.create({ data: { runId: run.id, title: `${slug} bug`, severity: "high", category: "network", pageUrl: run.targetUrl, source: "deterministic", reproSteps: [], evidence: {} } });
  return { workspace, run };
}

describe.skipIf(!hasTestDb)("row-level security", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, runs, steps, bugs CASCADE");
  });

  it("a query without any WHERE sees only its own workspace, children included", async () => {
    const a = await workspaceWithRun("a");
    await workspaceWithRun("b");
    const asA = tenantDb(a.workspace.id);
    expect((await asA.run.findMany()).map((r) => r.id)).toEqual([a.run.id]);
    expect((await asA.bug.findMany()).map((b) => b.title)).toEqual(["a bug"]);
    expect(await asA.step.count()).toBe(1);
    expect((await asA.workspace.findMany()).map((w) => w.slug)).toEqual(["a"]);
  });

  it("the web role's plain client sees no tenant rows at all: forgetting tenantDb fails closed (run 5)", async () => {
    await workspaceWithRun("a");
    const [role] = await appDb.$queryRaw<{ name: string; superuser: boolean; bypass: boolean }[]>`
      SELECT current_user AS name, rolsuper AS superuser, rolbypassrls AS bypass FROM pg_roles WHERE rolname = current_user`;
    expect(role).toEqual({ name: "ata_web", superuser: false, bypass: false });
    expect(await appDb.run.count()).toBe(0);
    expect(await appDb.workspace.count()).toBe(0);
    await expect(appDb.$executeRawUnsafe("ALTER TABLE runs DISABLE ROW LEVEL SECURITY")).rejects.toThrow();
  });

  it("can't write into another workspace or change its rows", async () => {
    const a = await workspaceWithRun("a");
    const b = await workspaceWithRun("b");
    const asA = tenantDb(a.workspace.id);
    await expect(asA.run.create({ data: { workspaceId: b.workspace.id, targetUrl: "https://x.test/", mode: "passive" } })).rejects.toThrow();
    expect((await asA.run.updateMany({ where: { id: b.run.id }, data: { status: "failed" } })).count).toBe(0);
    expect((await db.run.findUniqueOrThrow({ where: { id: b.run.id } })).status).toBe("done");
  });

  it("a transaction that forgot to set the workspace sees nothing (fails closed)", async () => {
    await workspaceWithRun("a");
    const rows = await db.$transaction(async (tx) => {
      await tx.$executeRawUnsafe("SET LOCAL ROLE app_tenant");
      return tx.$queryRawUnsafe<{ n: bigint }[]>("SELECT count(*) AS n FROM runs");
    });
    expect(Number(rows[0].n)).toBe(0);
  });

  it("the owning role (migrations, the worker) is not filtered", async () => {
    await workspaceWithRun("a");
    await workspaceWithRun("b");
    expect(await db.run.count()).toBe(2);
  });
});
