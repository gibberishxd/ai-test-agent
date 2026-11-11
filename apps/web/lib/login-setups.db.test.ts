/** Run 4, J2: sign-in setups against a real Postgres (test/global-setup.ts). */
import { randomBytes } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { db } from "@/lib/db";
import { deleteLoginSetup, listLoginSetups, requestLoginCheck, saveLoginSetup } from "@/lib/login-setups";
import { decryptSecret } from "@/lib/secret-box";
import { hasTestDb } from "../test/use-test-db";

const KEY = randomBytes(32);
const FORM = {
  targetUrl: "https://staging.example.com/",
  kind: "form",
  loginUrl: "https://staging.example.com/login",
  username: "qa@example.com",
  password: "s3cret-Pass!",
};

async function workspace(slug: string) {
  return db.workspace.create({ data: { name: slug, slug } });
}

describe.skipIf(!hasTestDb)("sign-in setups (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, login_setups CASCADE");
  });

  it("stores the password only encrypted, and never returns or logs it", async () => {
    const log = vi.spyOn(console, "log");
    const a = await workspace("a");
    const saved = await saveLoginSetup(a.id, FORM, KEY);
    expect(saved.ok).toBe(true);
    const row = await db.loginSetup.findFirstOrThrow({ where: { workspaceId: a.id } });
    expect(row.passwordCiphertext).not.toContain("s3cret");
    expect(decryptSecret(row.passwordCiphertext!, a.id, KEY)).toBe("s3cret-Pass!");
    const listed = JSON.stringify(await listLoginSetups(a.id));
    expect(listed).not.toContain("s3cret");
    expect(listed).not.toContain(row.passwordCiphertext!);
    expect(JSON.stringify(log.mock.calls)).not.toContain("s3cret");
  });

  it("an edit without a password keeps the saved one; one setup per site", async () => {
    const a = await workspace("a");
    await saveLoginSetup(a.id, FORM, KEY);
    await saveLoginSetup(a.id, { ...FORM, password: "", successSelector: "#account" }, KEY);
    const rows = await db.loginSetup.findMany({ where: { workspaceId: a.id } });
    expect(rows).toHaveLength(1);
    expect(decryptSecret(rows[0].passwordCiphertext!, a.id, KEY)).toBe("s3cret-Pass!");
    expect(rows[0].successSelector).toBe("#account");
  });

  it("Test sign-in queues a check; saving again clears the old result", async () => {
    const a = await workspace("a");
    const saved = await saveLoginSetup(a.id, FORM, KEY);
    if (!saved.ok) throw new Error("not saved");
    const requested = await requestLoginCheck(a.id, saved.setup.id);
    expect(requested?.checking).toBe(true);
    await db.loginSetup.update({ where: { id: saved.setup.id }, data: { checkRequestedAt: null, lastCheck: { ok: true, detail: "signed in", checkedAt: "x" } } });
    await saveLoginSetup(a.id, { ...FORM, password: "new-Pass!" }, KEY);
    const [view] = await listLoginSetups(a.id);
    expect(view.lastCheck).toBeNull();
  });

  it("workspace B can't see, test or delete workspace A's setup, and A's ciphertext doesn't decrypt as B's", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    const saved = await saveLoginSetup(a.id, FORM, KEY);
    if (!saved.ok) throw new Error("not saved");
    expect(await listLoginSetups(b.id)).toEqual([]);
    expect(await requestLoginCheck(b.id, saved.setup.id)).toBeNull();
    expect(await deleteLoginSetup(b.id, saved.setup.id)).toBe(false);
    const row = await db.loginSetup.findFirstOrThrow({ where: { workspaceId: a.id } });
    expect(() => decryptSecret(row.passwordCiphertext!, b.id, KEY)).toThrow();
    expect(await deleteLoginSetup(a.id, saved.setup.id)).toBe(true);
  });
});
