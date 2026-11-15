/** Run 7, M3: targets and specs through /api/v1 against a real Postgres, as a CI script calls them. */
import { beforeEach, describe, expect, it } from "vitest";
import { GET as listTargetsRoute, POST as createTargetRoute } from "@/app/api/v1/targets/route";
import { GET as listSpecsRoute, POST as createSpecRoute } from "@/app/api/v1/targets/[id]/specs/route";
import { DELETE as deleteSpecRoute, PATCH as updateSpecRoute } from "@/app/api/v1/specs/[id]/route";
import { createApiKey } from "@/lib/api-keys";
import { adminDb as db } from "../test/admin-db";
import { hasTestDb } from "../test/use-test-db";

async function keyFor(slug: string) {
  const workspace = await db.workspace.create({ data: { name: slug, slug } });
  return (await createApiKey(workspace.id, null, "CI")).key;
}

function request(path: string, key: string, method = "GET", body?: unknown) {
  return new Request(`http://app.test${path}`, {
    method,
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}
const params = (id: string) => ({ params: Promise.resolve({ id }) });

describe.skipIf(!hasTestDb)("/api/v1 targets and specs (database)", () => {
  beforeEach(async () => {
    await db.$executeRawUnsafe("TRUNCATE workspaces, api_keys, api_rate_windows CASCADE");
  });

  it("adds a target by URL, keeps its origin, and returns the same one for the same origin", async () => {
    const key = await keyFor("a");
    const first = await createTargetRoute(request("/api/v1/targets", key, "POST", { url: "https://shop.test/cart", name: "Shop" }));
    expect(first.status).toBe(201);
    const { target } = await first.json();
    expect(target).toMatchObject({ origin: "https://shop.test", name: "Shop", specs: 0, flows: 0 });
    const again = await (await createTargetRoute(request("/api/v1/targets", key, "POST", { url: "https://shop.test/" }))).json();
    expect(again.target.id).toBe(target.id);
    const list = await (await listTargetsRoute(request("/api/v1/targets", key))).json();
    expect(list.targets.map((t: { id: string }) => t.id)).toEqual([target.id]);
  });

  it("adds, lists, edits and deletes a spec; an edit makes it wait for embedding again", async () => {
    const key = await keyFor("a");
    const { target } = await (await createTargetRoute(request("/api/v1/targets", key, "POST", { url: "https://shop.test" }))).json();
    const created = await createSpecRoute(request(`/api/v1/targets/${target.id}/specs`, key, "POST", { title: "Checkout", body: "## Email\n- A valid email is required." }), params(target.id));
    expect(created.status).toBe(201);
    const { spec } = await created.json();
    expect(spec).toMatchObject({ title: "Checkout", status: "waiting", chunks: 0 });

    // The worker embeds it: chunked_at catches up with updated_at.
    await db.$executeRawUnsafe(`UPDATE specs SET chunked_at = updated_at + interval '1 second' WHERE id = '${spec.id}'`);
    const listed = await (await listSpecsRoute(request(`/api/v1/targets/${target.id}/specs`, key), params(target.id))).json();
    expect(listed.specs[0].status).toBe("ready");

    const edited = await updateSpecRoute(request(`/api/v1/specs/${spec.id}`, key, "PATCH", { title: "Checkout", body: "## Email\n- Changed." }), params(spec.id));
    expect(edited.status).toBe(200);
    expect((await edited.json()).spec).toMatchObject({ body: "## Email\n- Changed.", status: "waiting" });

    expect((await deleteSpecRoute(request(`/api/v1/specs/${spec.id}`, key, "DELETE"), params(spec.id))).status).toBe(204);
    expect((await deleteSpecRoute(request(`/api/v1/specs/${spec.id}`, key, "DELETE"), params(spec.id))).status).toBe(404);
  });

  it("refuses an invalid spec with field errors", async () => {
    const key = await keyFor("a");
    const { target } = await (await createTargetRoute(request("/api/v1/targets", key, "POST", { url: "https://shop.test" }))).json();
    const response = await createSpecRoute(request(`/api/v1/targets/${target.id}/specs`, key, "POST", { title: "", body: "" }), params(target.id));
    expect(response.status).toBe(400);
    expect(Object.keys((await response.json()).errors).sort()).toEqual(["body", "title"]);
  });

  it("never shows or changes another workspace's targets and specs", async () => {
    const mine = await keyFor("a");
    const theirs = await keyFor("b");
    const { target } = await (await createTargetRoute(request("/api/v1/targets", mine, "POST", { url: "https://shop.test" }))).json();
    const { spec } = await (await createSpecRoute(request(`/api/v1/targets/${target.id}/specs`, mine, "POST", { title: "T", body: "B" }), params(target.id))).json();

    expect((await (await listTargetsRoute(request("/api/v1/targets", theirs))).json()).targets).toEqual([]);
    expect((await listSpecsRoute(request(`/api/v1/targets/${target.id}/specs`, theirs), params(target.id))).status).toBe(404);
    expect((await createSpecRoute(request(`/api/v1/targets/${target.id}/specs`, theirs, "POST", { title: "T", body: "B" }), params(target.id))).status).toBe(404);
    expect((await updateSpecRoute(request(`/api/v1/specs/${spec.id}`, theirs, "PATCH", { title: "X", body: "Y" }), params(spec.id))).status).toBe(404);
    expect((await deleteSpecRoute(request(`/api/v1/specs/${spec.id}`, theirs, "DELETE"), params(spec.id))).status).toBe(404);
    expect((await db.spec.findUniqueOrThrow({ where: { id: spec.id } })).body).toBe("B");
  });
});
