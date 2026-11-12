/** Run 4, J3: webhook endpoints against a real Postgres. */
import { randomBytes } from "node:crypto";
import { beforeEach, describe, expect, it } from "vitest";
import { adminDb as db } from "../test/admin-db";
import { decryptSecret } from "@/lib/secret-box";
import { createWebhook, deleteWebhook, listWebhooks } from "@/lib/webhooks";
import { hasTestDb } from "../test/use-test-db";

const KEY = randomBytes(32);

async function workspace(slug: string) {
  return db.workspace.create({ data: { name: slug, slug } });
}

describe.skipIf(!hasTestDb)("webhooks (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, webhook_endpoints, webhook_deliveries CASCADE");
  });

  it("shows the signing secret once and stores it encrypted", async () => {
    const a = await workspace("a");
    const created = await createWebhook(a.id, "https://hooks.example.com/ata", KEY);
    if (!created.ok) throw new Error("not created");
    const row = await db.webhookEndpoint.findFirstOrThrow();
    expect(row.secretCiphertext).not.toContain(created.secret);
    expect(decryptSecret(row.secretCiphertext, a.id, KEY)).toBe(created.secret);
    expect(JSON.stringify(await listWebhooks(a.id))).not.toContain(created.secret);
  });

  it("lists the recent deliveries with their outcome", async () => {
    const a = await workspace("a");
    const created = await createWebhook(a.id, "https://hooks.example.com/ata", KEY);
    if (!created.ok) throw new Error("not created");
    await db.webhookDelivery.create({
      data: { endpointId: created.webhook.id, event: "run.finished", payload: {}, status: "failed", attempts: 6, lastStatusCode: 500, lastError: "HTTP 500" },
    });
    const [listed] = await listWebhooks(a.id);
    expect(listed.deliveries).toMatchObject([{ event: "run.finished", status: "failed", attempts: 6, lastStatusCode: 500 }]);
  });

  it("refuses internal URLs, and workspace B can't see or delete A's webhook", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    expect(await createWebhook(a.id, "http://169.254.169.254/", KEY)).toMatchObject({ ok: false });
    const created = await createWebhook(a.id, "https://hooks.example.com/ata", KEY);
    if (!created.ok) throw new Error("not created");
    expect(await listWebhooks(b.id)).toEqual([]);
    expect(await deleteWebhook(b.id, created.webhook.id)).toBe(false);
    expect(await deleteWebhook(a.id, created.webhook.id)).toBe(true);
  });
});
