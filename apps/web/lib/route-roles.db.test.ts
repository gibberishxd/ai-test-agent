/**
 * Every protected route, for every role (run 4, J5). A role the table doesn't allow gets 403; a
 * role it allows gets past the check (any other status: 2xx, or 400/404 for the made-up input).
 * Only `currentUser` is stubbed: the role is read from the database like in production.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminDb as db } from "../test/admin-db";
import { can, ROLES, type Action, type Role } from "@/lib/roles";
import { hasTestDb } from "../test/use-test-db";

const session = vi.hoisted(() => ({ user: null as null | { id: string; workspaceId: string; email: string; name: null } }));
vi.mock("@/lib/auth", () => ({ currentUser: async () => session.user }));

const ID = "00000000-0000-4000-8000-000000000000";
const json = (body: unknown, method = "POST") =>
  new Request("http://app.test/x", { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const params = { params: Promise.resolve({ id: ID }) };

type Case = [string, Action, () => Promise<Response>];
const cases: Case[] = [
  ["POST /api/domains", "domains.manage", async () => (await import("@/app/api/domains/route")).POST(json({ hostname: "example.com" }))],
  ["POST /api/domains/{id}/verify", "domains.manage", async () => (await import("@/app/api/domains/[id]/verify/route")).POST(json({}), params)],
  ["POST /api/models", "models.manage", async () => (await import("@/app/api/models/route")).POST(json({}))],
  ["PATCH /api/models/{id}", "models.manage", async () => (await import("@/app/api/models/[id]/route")).PATCH(json({ isDefault: true }, "PATCH"), params)],
  ["DELETE /api/models/{id}", "models.manage", async () => (await import("@/app/api/models/[id]/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/models/{id}/test", "models.manage", async () => (await import("@/app/api/models/[id]/test/route")).POST(json({}), params)],
  ["POST /api/login-setups", "login_setups.manage", async () => (await import("@/app/api/login-setups/route")).POST(json({}))],
  ["DELETE /api/login-setups/{id}", "login_setups.manage", async () => (await import("@/app/api/login-setups/[id]/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/login-setups/{id}/test", "login_setups.manage", async () => (await import("@/app/api/login-setups/[id]/test/route")).POST(json({}), params)],
  ["POST /api/api-keys", "api_keys.manage", async () => (await import("@/app/api/api-keys/route")).POST(json({ name: "CI" }))],
  ["DELETE /api/api-keys/{id}", "api_keys.manage", async () => (await import("@/app/api/api-keys/[id]/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/webhooks", "webhooks.manage", async () => (await import("@/app/api/webhooks/route")).POST(json({ url: "ftp://x" }))],
  ["PATCH /api/webhooks/{id}", "webhooks.manage", async () => (await import("@/app/api/webhooks/[id]/route")).PATCH(json({ enabled: false }, "PATCH"), params)],
  ["DELETE /api/webhooks/{id}", "webhooks.manage", async () => (await import("@/app/api/webhooks/[id]/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/bugs/{id}/triage", "finding.triage", async () => (await import("@/app/api/bugs/[id]/triage/route")).POST(json({ state: "confirmed" }), params)],
  ["POST /api/runs/{id}/share", "run.share", async () => (await import("@/app/api/runs/[id]/share/route")).POST(json({}), params)],
  ["DELETE /api/runs/{id}/share", "run.share", async () => (await import("@/app/api/runs/[id]/share/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/runs/{id}/stop", "run.stop", async () => (await import("@/app/api/runs/[id]/stop/route")).POST(json({}), params)],
  ["POST /api/runs", "run.start", async () => (await import("@/app/api/runs/route")).POST(json({ targetUrl: "http://localhost:5173", mode: "passive" }))],
  ["GET /api/members", "settings.view", async () => (await import("@/app/api/members/route")).GET()],
  ["PATCH /api/members/{id}", "members.manage", async () => (await import("@/app/api/members/[id]/route")).PATCH(json({ role: "viewer" }, "PATCH"), params)],
  ["DELETE /api/members/{id}", "members.manage", async () => (await import("@/app/api/members/[id]/route")).DELETE(json({}, "DELETE"), params)],
  ["POST /api/members/{id}/owner", "workspace.transfer", async () => (await import("@/app/api/members/[id]/owner/route")).POST(json({}), params)],
  ["POST /api/invitations", "members.manage", async () => (await import("@/app/api/invitations/route")).POST(json({ role: "viewer" }))],
  ["DELETE /api/invitations/{id}", "members.manage", async () => (await import("@/app/api/invitations/[id]/route")).DELETE(json({}, "DELETE"), params)],
];

describe.skipIf(!hasTestDb)("every protected route checks the role", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, users, runs, audit_log, invitations, api_keys, webhook_endpoints, login_setups, model_configs, domains CASCADE");
  });

  for (const role of ROLES) {
    it(`as ${role}`, async () => {
      const workspace = await db.workspace.create({ data: { name: "w", slug: `w-${role}`, monthlyRunQuota: 100 } });
      const user = await db.user.create({ data: { email: `${role}@example.com`, workspaceId: workspace.id, role: role as Role } });
      session.user = { id: user.id, workspaceId: workspace.id, email: user.email, name: null };
      for (const [name, action, call] of cases) {
        const status = (await call()).status;
        if (can(role, action)) expect(status, `${role}: ${name}`).not.toBe(403);
        else expect(status, `${role}: ${name}`).toBe(403);
      }
    });
  }

  it("signed out, management routes answer 401", async () => {
    session.user = null;
    for (const [name, action, call] of cases) {
      if (["run.start", "run.stop"].includes(action)) continue; // visitors may try the demo
      expect((await call()).status, name).toBe(401);
    }
  });
});
