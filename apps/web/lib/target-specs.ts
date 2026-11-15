/**
 * Targets, and a team's own requirements for each (run 7, M3; roadmap item 1). A target is an
 * app a workspace tests, by origin. Its specs (user stories, acceptance criteria, as Markdown or
 * plain text) are chunked and embedded by the worker before a run on that origin, and the agent
 * and the verifier test against the parts closest to each page. Every query goes through the
 * tenant client: row-level security keeps workspaces apart.
 */
import { inTenant, tenantDb, workspaceOf, type TenantContext } from "@/lib/tenant-db";

export const MAX_SPEC_CHARS = 100_000; // the database's own limit (specs_body_length)
export const MAX_TITLE_CHARS = 200;

type Result<T, F extends string> = { ok: true; value: T } | { ok: false; errors: Partial<Record<F, string>> };

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

export function originOf(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.origin : null;
  } catch {
    return null;
  }
}

export function parseTargetInput(body: Record<string, unknown>): Result<{ origin: string; name: string | null }, "url" | "name"> {
  const origin = originOf(text(body.url));
  if (!origin) return { ok: false, errors: { url: "Enter the app's address, e.g. https://staging.example.com." } };
  const name = text(body.name).slice(0, 100) || null;
  return { ok: true, value: { origin, name } };
}

export function parseSpecInput(body: Record<string, unknown>): Result<{ title: string; body: string }, "title" | "body"> {
  const errors: Partial<Record<"title" | "body", string>> = {};
  const title = text(body.title);
  const content = typeof body.body === "string" ? body.body.replace(/\r\n/g, "\n").trim() : "";
  if (!title) errors.title = "Give the spec a title, e.g. Checkout.";
  else if (title.length > MAX_TITLE_CHARS) errors.title = `At most ${MAX_TITLE_CHARS} characters.`;
  if (!content) errors.body = "Paste the requirements: user stories, acceptance criteria.";
  else if (content.length > MAX_SPEC_CHARS) errors.body = `At most ${MAX_SPEC_CHARS.toLocaleString("en")} characters; split it into several specs.`;
  if (Object.keys(errors).length) return { ok: false, errors };
  return { ok: true, value: { title, body: content } };
}

/** "ready": the worker has embedded this version. "waiting": it will, before the next run on the target. */
export function specStatus(spec: { chunkedAt: Date | null; updatedAt: Date }): "ready" | "waiting" {
  return spec.chunkedAt && spec.chunkedAt >= spec.updatedAt ? "ready" : "waiting";
}

export type TargetView = { id: string; origin: string; name: string | null; specs: number; flows: number; createdAt: string };
export type SpecView = { id: string; targetId: string; title: string; body: string; status: "ready" | "waiting"; chunks: number; updatedAt: string };

export async function listTargets(scope: string | TenantContext): Promise<TargetView[]> {
  const workspaceId = workspaceOf(scope);
  const rows = await tenantDb(scope).target.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "asc" },
    include: { _count: { select: { specs: true, flows: true } } },
  });
  return rows.map((t) => ({
    id: t.id,
    origin: t.origin,
    name: t.name,
    specs: t._count.specs,
    flows: t._count.flows,
    createdAt: t.createdAt.toISOString(),
  }));
}

export async function getTarget(scope: string | TenantContext, id: string): Promise<TargetView | null> {
  if (!isUuid(id)) return null;
  return (await listTargets(scope)).find((t) => t.id === id) ?? null;
}

/** Create a target, or return the workspace's existing one for that origin. */
export async function saveTarget(scope: string | TenantContext, body: Record<string, unknown>) {
  const parsed = parseTargetInput(body);
  if (!parsed.ok) return parsed;
  const workspaceId = workspaceOf(scope);
  const { origin, name } = parsed.value;
  const row = await tenantDb(scope).target.upsert({
    where: { workspaceId_origin: { workspaceId, origin } },
    create: { workspaceId, origin, name },
    update: name ? { name } : {},
  });
  return { ok: true as const, target: (await getTarget(scope, row.id))! };
}

export async function deleteTarget(scope: string | TenantContext, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const { count } = await tenantDb(scope).target.deleteMany({ where: { id, workspaceId: workspaceOf(scope) } });
  return count > 0;
}

export async function listSpecs(scope: string | TenantContext, targetId: string): Promise<SpecView[]> {
  if (!isUuid(targetId)) return [];
  const rows = await tenantDb(scope).spec.findMany({
    where: { targetId, workspaceId: workspaceOf(scope) },
    orderBy: { createdAt: "asc" },
    include: { _count: { select: { chunks: true } } },
  });
  return rows.map(toSpecView);
}

export async function createSpec(scope: string | TenantContext, targetId: string, body: Record<string, unknown>) {
  const parsed = parseSpecInput(body);
  if (!parsed.ok) return parsed;
  const target = await getTarget(scope, targetId);
  if (!target) return { ok: false as const, notFound: true as const, errors: {} };
  const row = await tenantDb(scope).spec.create({
    data: { workspaceId: workspaceOf(scope), targetId, ...parsed.value },
    include: { _count: { select: { chunks: true } } },
  });
  return { ok: true as const, spec: toSpecView(row) };
}

export async function updateSpec(scope: string | TenantContext, id: string, body: Record<string, unknown>) {
  const parsed = parseSpecInput(body);
  if (!parsed.ok) return parsed;
  if (!isUuid(id)) return { ok: false as const, notFound: true as const, errors: {} };
  const row = await inTenant(scope, async (tx) => {
    // chunkedAt null: the worker embeds the new text before the next run on the target.
    const { count } = await tx.spec.updateMany({ where: { id, workspaceId: workspaceOf(scope) }, data: { ...parsed.value, chunkedAt: null } });
    return count ? tx.spec.findUniqueOrThrow({ where: { id }, include: { _count: { select: { chunks: true } } } }) : null;
  });
  if (!row) return { ok: false as const, notFound: true as const, errors: {} };
  return { ok: true as const, spec: toSpecView(row) };
}

export async function deleteSpec(scope: string | TenantContext, id: string): Promise<boolean> {
  if (!isUuid(id)) return false;
  const { count } = await tenantDb(scope).spec.deleteMany({ where: { id, workspaceId: workspaceOf(scope) } });
  return count > 0;
}

type SpecRow = { id: string; targetId: string; title: string; body: string; chunkedAt: Date | null; updatedAt: Date; _count: { chunks: number } };

function toSpecView(row: SpecRow): SpecView {
  return {
    id: row.id,
    targetId: row.targetId,
    title: row.title,
    body: row.body,
    status: specStatus(row),
    chunks: row._count.chunks,
    updatedAt: row.updatedAt.toISOString(),
  };
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
