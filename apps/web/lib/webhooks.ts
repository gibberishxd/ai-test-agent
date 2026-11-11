/**
 * A workspace's webhook endpoints (run 4, J3). When a run finishes, the worker POSTs a signed
 * `run.finished` event to each enabled endpoint (apps/worker/src/worker/webhooks.py) and logs
 * every delivery.
 *
 * The signing secret is shown once, when the endpoint is created; it is stored encrypted (the
 * worker must read it to sign). The URL is checked here for the obvious mistakes, and checked
 * again by the worker at send time, after DNS, through the same SSRF guard as the browser.
 */
import { randomBytes } from "node:crypto";
import { isIP } from "node:net";
import { db } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
import { encryptSecret } from "@/lib/secret-box";

export type DeliveryView = {
  id: string;
  event: string;
  status: string;
  attempts: number;
  lastStatusCode: number | null;
  lastError: string | null;
  createdAt: string;
  deliveredAt: string | null;
};

export type WebhookView = { id: string; url: string; enabled: boolean; createdAt: string; deliveries: DeliveryView[] };

const RECENT_DELIVERIES = 10;

export function generateWebhookSecret(): string {
  return "whsec_" + randomBytes(32).toString("base64url");
}

function privateIp(host: string): boolean {
  const ip = host.replace(/^\[|\]$/g, "");
  if (isIP(ip) === 6) return ip === "::1" || /^f[cd]/i.test(ip) || /^fe80/i.test(ip);
  if (isIP(ip) !== 4) return false;
  const [a, b] = ip.split(".").map(Number);
  return a === 10 || a === 127 || a === 0 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
}

/** null if the URL can be saved, otherwise why not. The worker checks again after DNS. */
export function webhookUrlError(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "Enter a full URL, starting with https://.";
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "Webhooks are sent over http(s) only.";
  if (url.username || url.password) return "Don't put credentials in the URL: verify the signature instead.";
  const host = url.hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".internal") || privateIp(host)) {
    return "Webhooks go to public addresses only, not to private or internal ones.";
  }
  return null;
}

type Row = Awaited<ReturnType<typeof db.webhookEndpoint.findFirstOrThrow>> & {
  deliveries?: Awaited<ReturnType<typeof db.webhookDelivery.findFirstOrThrow>>[];
};

function toView(row: Row): WebhookView {
  return {
    id: row.id,
    url: row.url,
    enabled: row.enabled,
    createdAt: row.createdAt.toISOString(),
    deliveries: (row.deliveries ?? []).map((d) => ({
      id: d.id,
      event: d.event,
      status: d.status,
      attempts: d.attempts,
      lastStatusCode: d.lastStatusCode,
      lastError: d.lastError,
      createdAt: d.createdAt.toISOString(),
      deliveredAt: d.deliveredAt?.toISOString() ?? null,
    })),
  };
}

export async function listWebhooks(workspaceId: string): Promise<WebhookView[]> {
  const rows = await tenantDb(workspaceId).webhookEndpoint.findMany({
    where: { workspaceId },
    orderBy: { createdAt: "asc" },
    include: { deliveries: { orderBy: { createdAt: "desc" }, take: RECENT_DELIVERIES } },
  });
  return rows.map(toView);
}

/** Returns the signing secret once. */
export async function createWebhook(workspaceId: string, url: string, serverKey: Buffer) {
  const trimmed = url.trim();
  const error = webhookUrlError(trimmed);
  if (error) return { ok: false as const, error };
  const secret = generateWebhookSecret();
  const row = await db.webhookEndpoint.create({
    data: { workspaceId, url: trimmed, secretCiphertext: encryptSecret(secret, workspaceId, serverKey) },
  });
  return { ok: true as const, secret, webhook: toView(row) };
}

export async function setWebhookEnabled(workspaceId: string, id: string, enabled: boolean): Promise<boolean> {
  return (await db.webhookEndpoint.updateMany({ where: { id, workspaceId }, data: { enabled } })).count > 0;
}

export async function deleteWebhook(workspaceId: string, id: string): Promise<boolean> {
  return (await db.webhookEndpoint.deleteMany({ where: { id, workspaceId } })).count > 0;
}
