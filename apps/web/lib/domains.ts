/**
 * Domain verification: a workspace proves it owns a domain before interactive tests may run
 * on it (typing and submitting forms on someone else's site isn't OK).
 *
 * Two ways, either is enough:
 * - DNS: a TXT record on the domain containing `ai-test-agent-verification=<token>`
 * - File: https://<domain>/.well-known/ai-test-agent.txt containing the token
 *
 * The file check makes our server fetch a URL a user typed, which is SSRF territory, so it
 * first resolves the host, refuses private/internal addresses, connects to exactly the address
 * it checked (no second DNS lookup), and doesn't follow redirects.
 */
import { lookup, resolveTxt } from "node:dns/promises";
import { get as httpGet } from "node:http";
import { get as httpsGet } from "node:https";

export const TXT_PREFIX = "ai-test-agent-verification=";
export const WELL_KNOWN_PATH = "/.well-known/ai-test-agent.txt";

export type VerifyDeps = {
  resolveTxt: (host: string) => Promise<string[][]>;
  resolveIps: (host: string) => Promise<string[]>;
  /** Fetch `url`, connecting to `ip` (an address of the URL's host that was already checked). */
  fetchText: (url: string, ip: string) => Promise<string | null>;
};

export type VerifyResult = { ok: true; method: "dns" | "file" } | { ok: false; reason: string };

/** "https://Shop.example.com/path" or "shop.example.com" → "shop.example.com". */
export function normalizeHostname(input: string): string | null {
  const raw = input.trim().toLowerCase();
  if (!raw) return null;
  try {
    const host = new URL(raw.includes("://") ? raw : `https://${raw}`).hostname;
    return /^[a-z0-9.-]+\.[a-z]{2,}$/.test(host) ? host : null;
  } catch {
    return null;
  }
}

/** True for addresses on the public internet; false for private, loopback, link-local etc. */
export function isPublicIp(ip: string): boolean {
  const v4 = ip.startsWith("::ffff:") ? ip.slice(7) : ip;
  if (/^\d+\.\d+\.\d+\.\d+$/.test(v4)) {
    const [a, b] = v4.split(".").map(Number);
    if (a === 10 || a === 127 || a === 0) return false;
    if (a === 169 && b === 254) return false; // link-local, cloud metadata
    if (a === 172 && b >= 16 && b <= 31) return false;
    if (a === 192 && b === 168) return false;
    if (a === 100 && b >= 64 && b <= 127) return false; // carrier-grade NAT
    if (a >= 224) return false; // multicast, reserved
    return true;
  }
  const v6 = ip.toLowerCase();
  if (v6 === "::1" || v6 === "::") return false;
  if (/^f[cd]/.test(v6)) return false; // fc00::/7 unique local
  if (/^fe[89ab]/.test(v6)) return false; // fe80::/10 link-local
  return true;
}

export async function verifyDomain(hostname: string, token: string, deps: VerifyDeps): Promise<VerifyResult> {
  try {
    const records = await deps.resolveTxt(hostname);
    if (records.some((parts) => parts.join("").trim() === `${TXT_PREFIX}${token}`)) {
      return { ok: true, method: "dns" };
    }
  } catch {
    // No TXT records (or DNS error): try the file next.
  }

  const ips = await deps.resolveIps(hostname).catch(() => []);
  if (ips.length === 0) return { ok: false, reason: `Couldn't resolve ${hostname}.` };
  if (!ips.every(isPublicIp)) {
    return { ok: false, reason: `${hostname} points to a private address; it can't be verified.` };
  }
  const body = await deps.fetchText(`https://${hostname}${WELL_KNOWN_PATH}`, ips[0]).catch(() => null);
  if (body?.trim() === token) return { ok: true, method: "file" };

  return {
    ok: false,
    reason: `No TXT record "${TXT_PREFIX}${token}" and no file at https://${hostname}${WELL_KNOWN_PATH} containing the token.`,
  };
}

type LookupCallback = (...args: unknown[]) => void;

/**
 * A DNS lookup that always answers `ip`. Given to the HTTP client so it connects to the
 * address we validated instead of resolving the name a second time: between two lookups a
 * hostile DNS server can swap a public address for a private one (DNS rebinding). The URL
 * keeps the hostname, so the Host header and the TLS certificate check still use it.
 */
export function pinnedLookup(ip: string) {
  const family = ip.includes(":") ? 6 : 4;
  return (_hostname: string, options: { all?: boolean }, callback: LookupCallback): void => {
    if (options.all) callback(null, [{ address: ip, family }]);
    else callback(null, ip, family);
  };
}

export const MAX_VERIFY_BYTES = 1024;
const VERIFY_TIMEOUT_MS = 5000;

/** GET `url` from `ip`: 5 s limit, no redirects, small 200 responses only. Otherwise null. */
export function fetchPinned(url: string, ip: string): Promise<string | null> {
  const get = url.startsWith("https:") ? httpsGet : httpGet;
  return new Promise((resolve) => {
    const request = get(url, { lookup: pinnedLookup(ip) as never, timeout: VERIFY_TIMEOUT_MS }, (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        return resolve(null);
      }
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk: string) => {
        body += chunk;
        if (body.length > MAX_VERIFY_BYTES) {
          request.destroy();
          resolve(null);
        }
      });
      response.on("end", () => resolve(body));
    });
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(null));
  });
}

/** Real network lookups. The file is fetched from the address that was just validated. */
export const realDeps: VerifyDeps = {
  resolveTxt: (host) => resolveTxt(host),
  resolveIps: async (host) => (await lookup(host, { all: true })).map((entry) => entry.address),
  fetchText: fetchPinned,
};
