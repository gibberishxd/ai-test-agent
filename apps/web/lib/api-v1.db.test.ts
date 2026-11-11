/** Run 4, J3: the /api/v1 route handlers against a real Postgres, as a CI script calls them. */
import { beforeEach, describe, expect, it } from "vitest";
import { POST as startRunRoute } from "@/app/api/v1/runs/route";
import { GET as getRunRoute } from "@/app/api/v1/runs/[id]/route";
import { GET as getReportRoute } from "@/app/api/v1/runs/[id]/report/route";
import { createApiKey, revokeApiKey } from "@/lib/api-keys";
import { db } from "@/lib/db";
import { hasTestDb } from "../test/use-test-db";

const DEMO = "http://localhost:5173";

async function workspace(slug: string) {
  return db.workspace.create({ data: { name: slug, slug, monthlyRunQuota: 2 } });
}

function request(path: string, key: string | null, body?: unknown) {
  return new Request(`http://app.test${path}`, {
    method: body ? "POST" : "GET",
    headers: { ...(key ? { authorization: `Bearer ${key}` } : {}), "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}
const params = (id: string) => ({ params: Promise.resolve({ id }) });

describe.skipIf(!hasTestDb)("/api/v1 (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, api_keys, api_rate_windows, runs, bugs, audit_log CASCADE");
  });

  it("refuses a request without a valid key", async () => {
    const response = await startRunRoute(request("/api/v1/runs", null, { target_url: DEMO }));
    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe("Bearer");
  });

  it("starts a run with the key's workspace, its budgets, and the key recorded", async () => {
    const a = await workspace("a");
    const { key, view } = await createApiKey(a.id, null, "CI");
    const response = await startRunRoute(request("/api/v1/runs", key, { target_url: DEMO, max_steps: 10, max_minutes: 5 }));
    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body).toMatchObject({ status: "queued", finished: false, links: { self: `http://app.test/api/v1/runs/${body.id}` } });
    const run = await db.run.findUniqueOrThrow({ where: { id: body.id } });
    expect(run).toMatchObject({ workspaceId: a.id, apiKeyId: view.id, maxSteps: 10, maxSeconds: 300, mode: "passive" });
    const audit = await db.auditLog.findFirstOrThrow({ where: { runId: run.id } });
    expect(audit.metadata).toMatchObject({ apiKeyId: view.id });
  });

  it("uses the dashboard's rules: quota, verified domains, field errors in API names", async () => {
    const a = await workspace("a");
    const { key } = await createApiKey(a.id, null, "CI");
    const invalid = await startRunRoute(request("/api/v1/runs", key, { target_url: "https://unverified.example.com", mode: "interactive" }));
    expect(invalid.status).toBe(400);
    expect((await invalid.json()).errors).toHaveProperty("mode");
    await startRunRoute(request("/api/v1/runs", key, { target_url: DEMO }));
    await startRunRoute(request("/api/v1/runs", key, { target_url: DEMO }));
    const overQuota = await startRunRoute(request("/api/v1/runs", key, { target_url: DEMO }));
    expect(overQuota.status).toBe(429);
  });

  it("reads status and reports only in the key's own workspace; JUnit on request", async () => {
    const a = await workspace("a");
    const b = await workspace("b");
    const keyA = (await createApiKey(a.id, null, "CI")).key;
    const keyB = (await createApiKey(b.id, null, "CI")).key;
    const run = await db.run.create({ data: { workspaceId: a.id, targetUrl: `${DEMO}/`, mode: "passive", status: "done" } });
    await db.bug.create({ data: { runId: run.id, title: "Profile API returns 500", severity: "high", category: "network", pageUrl: `${DEMO}/profile`, source: "deterministic", status: "confirmed", reproSteps: [], evidence: {} } });

    expect((await getRunRoute(request(`/api/v1/runs/${run.id}`, keyB), params(run.id))).status).toBe(404);
    const status = await (await getRunRoute(request(`/api/v1/runs/${run.id}`, keyA), params(run.id))).json();
    expect(status).toMatchObject({ finished: true, counts: { high: 1 } });

    const junit = await getReportRoute(request(`/api/v1/runs/${run.id}/report?format=junit`, keyA), params(run.id));
    expect(junit.headers.get("content-type")).toContain("application/xml");
    expect(await junit.text()).toContain('failures="1"');
  });

  it("a revoked key stops working at once", async () => {
    const a = await workspace("a");
    const { key, view } = await createApiKey(a.id, null, "CI");
    await revokeApiKey(a.id, view.id);
    expect((await startRunRoute(request("/api/v1/runs", key, { target_url: DEMO }))).status).toBe(401);
  });
});
