/**
 * M8 acceptance tests, against a real Postgres (test/global-setup.ts):
 * workspace isolation, domain verification, quota, share links, visitor limits.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createUserWithWorkspace } from "@/lib/auth-adapter";
import { adminDb as db } from "../test/admin-db";
import type { VerifyDeps } from "@/lib/domains";
import { getRun, listRuns, requestStop, startRun } from "@/lib/runs";
import { addDomain, checkDomain } from "@/lib/settings-data";
import {
  createModelConfig,
  deleteModelConfig,
  listModelConfigs,
  replaceModelKey,
  setDefaultModel,
  storeProbe,
} from "@/lib/model-configs";
import { canReadFile, createShareLink, getSharedRun, revokeShareLink } from "@/lib/share";
import type { RequestContext } from "@/lib/workspace";
import { hasTestDb } from "../test/use-test-db";

const DEMO = "http://localhost:5173/";

async function workspace(slug: string, quota = 50) {
  // Team plan: these tests bring their own hosted models, which the Free plan doesn't include.
  return db.workspace.create({ data: { name: slug, slug, monthlyRunQuota: quota, planId: "team" } });
}

function signedIn(workspaceId: string): RequestContext {
  return { workspaceId, userId: null, signedIn: true };
}

async function addRun(workspaceId: string, createdAt = new Date()) {
  return db.run.create({ data: { workspaceId, targetUrl: DEMO, mode: "passive", createdAt } });
}

describe.skipIf(!hasTestDb)("B2B foundations (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe(
      "TRUNCATE workspaces, users, runs, steps, bugs, audit_log, domains, accounts, verification_tokens, model_configs CASCADE",
    );
  });

  describe("workspace isolation", () => {
    it("a workspace can't read, stop or share another workspace's run", async () => {
      const a = await workspace("a");
      const b = await workspace("b");
      const run = await addRun(a.id);

      expect(await getRun(a.id, run.id)).not.toBeNull();
      expect(await getRun(b.id, run.id)).toBeNull();
      expect((await listRuns(b.id)).map((r) => r.id)).not.toContain(run.id);
      expect(await requestStop(b.id, run.id)).toBe(false);
      expect(await createShareLink(b.id, run.id)).toBeNull();
      expect(await revokeShareLink(b.id, run.id)).toBe(false);
    });

    it("can't verify another workspace's domain", async () => {
      const a = await workspace("a");
      const b = await workspace("b");
      const added = await addDomain(a.id, "shop.example.com");
      if (!added.ok) throw new Error(added.error);
      const result = await checkDomain(b.id, null, added.domain.id, passDns(b.verificationToken));
      expect(result.ok).toBe(false);
    });

    it("every new user gets their own workspace", async () => {
      const ada = await createUserWithWorkspace(db, { email: "ada@example.com", name: "Ada" });
      const bob = await createUserWithWorkspace(db, { email: "bob@example.com", name: "Bob" });
      expect(ada.workspaceId).not.toBe(bob.workspaceId);
    });
  });

  describe("domain verification", () => {
    it("a verified domain allows interactive runs on it", async () => {
      const a = await workspace("a");
      const added = await addDomain(a.id, "https://shop.example.com/cart");
      if (!added.ok) throw new Error(added.error);
      expect(added.domain.hostname).toBe("shop.example.com");

      const before = await startRun(signedIn(a.id), { targetUrl: "https://shop.example.com", mode: "interactive" }, "ip");
      expect(before.ok).toBe(false);

      const verified = await checkDomain(a.id, null, added.domain.id, passDns(a.verificationToken));
      expect(verified).toEqual({ ok: true, method: "dns" });
      const stored = await db.domain.findUniqueOrThrow({ where: { id: added.domain.id } });
      expect(stored.verifiedAt).not.toBeNull();
      expect(await db.auditLog.count({ where: { workspaceId: a.id, action: "domain.verified" } })).toBe(1);

      const after = await startRun(signedIn(a.id), { targetUrl: "https://shop.example.com", mode: "interactive" }, "ip");
      expect(after.ok).toBe(true);
    });

    it("a wrong token doesn't verify", async () => {
      const a = await workspace("a");
      const added = await addDomain(a.id, "shop.example.com");
      if (!added.ok) throw new Error(added.error);
      const result = await checkDomain(a.id, null, added.domain.id, passDns("someone-elses-token"));
      expect(result.ok).toBe(false);
    });
  });

  describe("quota", () => {
    it("holds under a burst of simultaneous requests", async () => {
      // Check-then-insert would let all of these through: each sees "1 run left".
      const a = await workspace("a", 3);
      const burst = Array.from({ length: 10 }, () =>
        startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive" }, "ip"),
      );
      const results = await Promise.all(burst);
      expect(results.filter((r) => r.ok)).toHaveLength(3);
      expect(await db.run.count({ where: { workspaceId: a.id } })).toBe(3);
    });

    it("refuses runs once the monthly quota is used", async () => {
      const a = await workspace("a", 2);
      await addRun(a.id);
      expect((await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive" }, "ip")).ok).toBe(true);
      const third = await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive" }, "ip");
      expect(third).toMatchObject({ ok: false, status: 429 });
    });

    it("doesn't count last month's runs", async () => {
      const a = await workspace("a", 1);
      const lastMonth = new Date();
      lastMonth.setUTCMonth(lastMonth.getUTCMonth() - 1);
      await addRun(a.id, lastMonth);
      expect((await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive" }, "ip")).ok).toBe(true);
    });
  });

  describe("share links", () => {
    it("serve a shared run's screenshots, and only that run's", async () => {
      const a = await workspace("a");
      const b = await workspace("b");
      const runA = await addRun(a.id);
      const runB = await addRun(a.id);
      const token = (await createShareLink(a.id, runA.id))!;

      // Someone with the link, who is in another workspace (or signed out).
      const outsider = { workspaceId: b.id, shareToken: token };
      expect(await canReadFile(`${runA.id}/page-001.png`, outsider)).toBe(true);
      expect(await canReadFile(`${runB.id}/page-001.png`, outsider)).toBe(false);
      expect(await canReadFile(`${runA.id}/page-001.png`, { workspaceId: b.id, shareToken: null })).toBe(false);
      expect(await canReadFile(`${runA.id}/page-001.png`, { workspaceId: b.id, shareToken: "x".repeat(32) })).toBe(false);

      // The owner needs no token; a revoked token stops working.
      expect(await canReadFile(`${runB.id}/page-001.png`, { workspaceId: a.id, shareToken: null })).toBe(true);
      await revokeShareLink(a.id, runA.id);
      expect(await canReadFile(`${runA.id}/page-001.png`, outsider)).toBe(false);
    });

    it("work until revoked", async () => {
      const a = await workspace("a");
      const run = await addRun(a.id);
      const token = await createShareLink(a.id, run.id);
      expect(token).toMatch(/^[A-Za-z0-9_-]{32}$/);
      expect(await createShareLink(a.id, run.id)).toBe(token); // the same link, not a new one
      expect((await getSharedRun(token!))?.id).toBe(run.id);

      expect(await revokeShareLink(a.id, run.id)).toBe(true);
      expect(await getSharedRun(token!)).toBeNull();
    });

    it("a made-up token finds nothing", async () => {
      expect(await getSharedRun("x".repeat(32))).toBeNull();
      expect(await getSharedRun("not-even-the-right-shape")).toBeNull();
    });
  });

  describe("visitors (not signed in)", () => {
    const visitor = (workspaceId: string): RequestContext => ({ workspaceId, userId: null, signedIn: false });

    it("can only test the demo shop", async () => {
      const pub = await workspace("demo");
      const result = await startRun(visitor(pub.id), { targetUrl: "https://example.com", mode: "passive" }, "1.2.3.4");
      expect(result).toMatchObject({ ok: false, status: 403 });
    });

    it("are rate limited per IP", async () => {
      const pub = await workspace("demo", 1000);
      for (let i = 0; i < 5; i++) {
        expect((await startRun(visitor(pub.id), { targetUrl: DEMO, mode: "passive" }, "1.2.3.4")).ok).toBe(true);
      }
      expect(await startRun(visitor(pub.id), { targetUrl: DEMO, mode: "passive" }, "1.2.3.4")).toMatchObject({ status: 429 });
      expect((await startRun(visitor(pub.id), { targetUrl: DEMO, mode: "passive" }, "5.6.7.8")).ok).toBe(true);
    });
  });

  describe("workspace models (bring your own model)", () => {
    const KEY = "sk-live-ABCD1234wxyz";
    const SERVER_KEY = Buffer.alloc(32, 9);
    const input = {
      label: "OpenRouter Gemini",
      provider: "openai-compat",
      baseUrl: "https://openrouter.example/api/v1",
      model: "google/gemini-3-flash",
      apiKey: KEY,
    };
    const passed = { ok: true, answers: true, tools: true, vision: true, error: null, checkedAt: "2026-11-10T12:00:00.000Z" };

    async function created(workspaceId: string) {
      const result = await createModelConfig(workspaceId, input, SERVER_KEY);
      if (!result.ok) throw new Error(JSON.stringify(result.errors));
      return result.model;
    }

    it("stores the key encrypted and never returns it", async () => {
      const a = await workspace("a");
      const model = await created(a.id);
      expect(model.keyHint).toBe("•••• wxyz");
      expect(JSON.stringify(model)).not.toContain(KEY);
      expect(JSON.stringify(await listModelConfigs(a.id))).not.toContain(KEY);

      const [row] = await db.$queryRawUnsafe<Record<string, unknown>[]>("SELECT * FROM model_configs");
      expect(JSON.stringify(row)).not.toContain(KEY);
      expect(JSON.stringify(row)).not.toContain("ABCD1234");
      expect(String(row!.api_key_ciphertext)).toMatch(/^v1:/);
    });

    it("never logs the key", async () => {
      const lines: string[] = [];
      const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) =>
        vi.spyOn(console, level).mockImplementation((...args: unknown[]) => void lines.push(args.map(String).join(" "))),
      );
      try {
        const a = await workspace("a");
        const model = await created(a.id);
        await replaceModelKey(a.id, model.id, "sk-live-NEWKEY9999", SERVER_KEY);
        await storeProbe(a.id, model.id, passed);
      } finally {
        spies.forEach((spy) => spy.mockRestore());
      }
      expect(lines.join("\n")).not.toContain(KEY);
      expect(lines.join("\n")).not.toContain("NEWKEY9999");
    });

    it("can be replaced and deleted, and the old key is gone", async () => {
      const a = await workspace("a");
      const model = await created(a.id);
      const replaced = await replaceModelKey(a.id, model.id, "sk-live-NEWKEY9999", SERVER_KEY);
      expect(replaced?.keyHint).toBe("•••• 9999");
      expect(replaced?.probe).toBeNull(); // a new key must be tested again
      expect(await deleteModelConfig(a.id, model.id)).toBe(true);
      expect(await listModelConfigs(a.id)).toEqual([]);
    });

    it("workspace B can't see, change, delete or use workspace A's model", async () => {
      const a = await workspace("a");
      const b = await workspace("b");
      const model = await created(a.id);
      await storeProbe(a.id, model.id, passed);

      expect(await listModelConfigs(b.id)).toEqual([]);
      expect(await replaceModelKey(b.id, model.id, "sk-evil", SERVER_KEY)).toBeNull();
      expect(await setDefaultModel(b.id, model.id)).toBe(false);
      expect(await storeProbe(b.id, model.id, passed)).toBe(false);
      expect(await deleteModelConfig(b.id, model.id)).toBe(false);

      const stolen = await startRun(signedIn(b.id), { targetUrl: DEMO, mode: "passive", modelConfigId: model.id }, "ip");
      expect(stolen).toMatchObject({ ok: false, status: 400 });
      expect(await db.run.count({ where: { workspaceId: b.id } })).toBe(0);
    });

    it("a run can only use a model that passed Test connection, and records it", async () => {
      const a = await workspace("a");
      const model = await created(a.id);
      const untested = await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive", modelConfigId: model.id }, "ip");
      expect(untested).toMatchObject({ ok: false, status: 400 });
      if (!untested.ok) expect(untested.errors.model).toMatch(/Test connection/);

      await storeProbe(a.id, model.id, { ...passed, ok: false, vision: false, error: "no images" });
      const blind = await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive", modelConfigId: model.id }, "ip");
      if (!blind.ok) expect(blind.errors.model).toMatch(/no images/);

      await storeProbe(a.id, model.id, passed);
      const started = await startRun(signedIn(a.id), { targetUrl: DEMO, mode: "passive", modelConfigId: model.id }, "ip");
      if (!started.ok) throw new Error(JSON.stringify(started.errors));
      expect((await db.run.findUniqueOrThrow({ where: { id: started.id } })).modelConfigId).toBe(model.id);
    });

    it("one default per workspace", async () => {
      const a = await workspace("a");
      const first = await created(a.id);
      const second = await created(a.id);
      await setDefaultModel(a.id, first.id);
      await setDefaultModel(a.id, second.id);
      const models = await listModelConfigs(a.id);
      expect(models.filter((m) => m.isDefault).map((m) => m.id)).toEqual([second.id]);
    });

    it("the database itself refuses a second default in one workspace (run 4, J5)", async () => {
      const a = await workspace("a");
      const b = await workspace("b");
      const first = await created(a.id);
      const second = await created(a.id);
      await db.modelConfig.update({ where: { id: first.id }, data: { isDefault: true } });
      // Code that forgets setDefaultModel's "unset the others first" fails instead of corrupting.
      await expect(db.modelConfig.update({ where: { id: second.id }, data: { isDefault: true } })).rejects.toThrow();
      const other = await created(b.id);
      await db.modelConfig.update({ where: { id: other.id }, data: { isDefault: true } }); // another workspace: fine
    });
  });

});

/** Fake DNS that has the TXT record for `token`. */
function passDns(token: string): VerifyDeps {
  return {
    resolveTxt: async () => [[`ai-test-agent-verification=${token}`]],
    resolveIps: async () => ["93.184.215.14"],
    fetchText: async () => null,
  };
}
