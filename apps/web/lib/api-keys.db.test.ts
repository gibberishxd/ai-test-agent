/** Run 4, J3: API keys against a real Postgres. */
import { beforeEach, describe, expect, it } from "vitest";
import { authenticateApiKey, createApiKey, listApiKeys, rateLimit, revokeApiKey } from "@/lib/api-keys";
import { db } from "@/lib/db";
import { hasTestDb } from "../test/use-test-db";

async function workspace(slug: string) {
  return db.workspace.create({ data: { name: slug, slug } });
}

const auth = (key: string) => authenticateApiKey(new Headers({ authorization: `Bearer ${key}` }));

describe.skipIf(!hasTestDb)("API keys (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, api_keys, api_rate_windows CASCADE");
  });

  it("is shown once, stored as a hash, and authenticates its workspace", async () => {
    const a = await workspace("a");
    const created = await createApiKey(a.id, null, "CI");
    const rows = await db.apiKey.findMany();
    expect(rows[0].keyHash).not.toContain(created.key.slice(4));
    const listed = JSON.stringify(await listApiKeys(a.id));
    expect(listed).not.toContain(created.key);
    expect(listed).toContain(created.view.prefix);
    expect(await auth(created.key)).toMatchObject({ workspaceId: a.id, keyId: created.view.id });
    expect((await db.apiKey.findFirstOrThrow()).lastUsedAt).not.toBeNull();
  });

  it("stops working when revoked, and a made-up key never works", async () => {
    const a = await workspace("a");
    const created = await createApiKey(a.id, null, "CI");
    expect(await revokeApiKey(a.id, created.view.id)).toBe(true);
    expect(await auth(created.key)).toBeNull();
    expect(await auth("ata_made_up_key_000000000000000000000000000")).toBeNull();
  });

  it("workspace B can't list or revoke workspace A's keys", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    const created = await createApiKey(a.id, null, "CI");
    expect(await listApiKeys(b.id)).toEqual([]);
    expect(await revokeApiKey(b.id, created.view.id)).toBe(false);
    expect(await auth(created.key)).not.toBeNull();
  });

  it("rate-limits per key per minute, even under parallel requests", async () => {
    const a = await workspace("a");
    const { view } = await createApiKey(a.id, null, "CI");
    const now = new Date("2026-11-11T10:00:30Z");
    const results = await Promise.all(Array.from({ length: 8 }, () => rateLimit(view.id, 5, now)));
    expect(results.filter((r) => r.ok)).toHaveLength(5);
    expect(results.find((r) => !r.ok)?.retryAfterS).toBe(30);
    expect((await rateLimit(view.id, 5, new Date("2026-11-11T10:01:01Z"))).ok).toBe(true); // next minute
  });
});
