/**
 * Signing in as the demo user twice at the same moment (two browser tabs, two e2e workers) must
 * give both the same user, not a unique-constraint error for the second (seen in CI, run 5).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { adminDb } from "../test/admin-db";
import { findOrCreateUser } from "@/lib/auth-adapter";
import { db } from "@/lib/db";
import { hasTestDb } from "../test/use-test-db";

describe.skipIf(!hasTestDb)("findOrCreateUser (database)", () => {
  beforeEach(async () => {
    await adminDb.$executeRawUnsafe("TRUNCATE workspaces, users CASCADE");
  });

  it("concurrent first sign-ins get one user and one workspace", async () => {
    const users = await Promise.all(Array.from({ length: 4 }, () => findOrCreateUser(db, { email: "demo-user@example.com", name: "Demo User" })));
    expect(new Set(users.map((u) => u.id)).size).toBe(1);
    expect(await adminDb.user.count()).toBe(1);
  });
});
