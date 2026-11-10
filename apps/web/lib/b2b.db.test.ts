/**
 * M8 acceptance tests, against a real Postgres (test/global-setup.ts):
 * workspace isolation, domain verification, quota, share links, visitor limits.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { createUserWithWorkspace } from "@/lib/auth-adapter";
import { db } from "@/lib/db";
import type { VerifyDeps } from "@/lib/domains";
import { getRun, listRuns, requestStop, startRun } from "@/lib/runs";
import { addDomain, checkDomain } from "@/lib/settings-data";
import { canReadFile, createShareLink, getSharedRun, revokeShareLink } from "@/lib/share";
import type { RequestContext } from "@/lib/workspace";
import { hasTestDb } from "../test/use-test-db";

const DEMO = "http://localhost:5173/";

async function workspace(slug: string, quota = 50) {
  return db.workspace.create({ data: { name: slug, slug, monthlyRunQuota: quota } });
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
      "TRUNCATE workspaces, users, runs, steps, bugs, audit_log, domains, accounts, verification_tokens CASCADE",
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
});

/** Fake DNS that has the TXT record for `token`. */
function passDns(token: string): VerifyDeps {
  return {
    resolveTxt: async () => [[`ai-test-agent-verification=${token}`]],
    resolveIps: async () => ["93.184.215.14"],
    fetchText: async () => null,
  };
}
