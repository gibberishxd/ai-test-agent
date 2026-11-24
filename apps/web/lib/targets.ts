/**
 * Which URLs a run may target, and in which mode. The worker enforces the same rules (and the
 * network guard on top); checking here too gives the user a clear message before queueing.
 */

export type RunMode = "passive" | "interactive";

/** Run 9: which agent drives an interactive run. "deep" is deep mode (DECISIONS D112). */
export type RunEngine = "loop" | "deep";

/** Deep mode's models, pinned IDs; the first is the default (DEEP_MODEL in the worker). */
export const DEEP_MODELS = ["claude-sonnet-5-5", "claude-opus-5-5"] as const;
export const DEEP_MODEL_LABELS: Record<(typeof DEEP_MODELS)[number], string> = {
  "claude-sonnet-5-5": "Claude Sonnet 5.5",
  "claude-opus-5-5": "Claude Opus 5.5",
};

export type RunInput = {
  targetUrl: string;
  mode: RunMode;
  focus: string | null;
  engine: RunEngine;
  /** Deep runs only: the model asked for; null = the worker's default. */
  engineModel: string | null;
};

export type FieldErrors = Partial<Record<"targetUrl" | "mode" | "focus" | "model" | "engineModel", string>>;

export type ParseResult = { ok: true; value: RunInput } | { ok: false; errors: FieldErrors };

export const MAX_FOCUS_LENGTH = 300;

export function demoUrl(): string {
  return process.env.DEMO_URL ?? "http://localhost:5173";
}

export function cleanDemoUrl(): string {
  return process.env.CLEAN_DEMO_URL ?? "http://localhost:5174";
}

/** Same scheme, host and port. */
export function sameOrigin(a: string, b: string): boolean {
  try {
    return new URL(a).origin === new URL(b).origin;
  } catch {
    return false;
  }
}

export function isDemoTarget(url: string): boolean {
  return sameOrigin(url, demoUrl()) || sameOrigin(url, cleanDemoUrl());
}

/** Validate the run form. `verifiedOrigins`: domains the workspace has verified. */
export function parseRunInput(
  input: { targetUrl?: unknown; mode?: unknown; focus?: unknown; engineModel?: unknown },
  verifiedOrigins: string[] = [],
): ParseResult {
  const errors: FieldErrors = {};

  const raw = typeof input.targetUrl === "string" ? input.targetUrl.trim() : "";
  let targetUrl = "";
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      errors.targetUrl = "Use an http:// or https:// URL.";
    } else {
      targetUrl = url.toString();
    }
  } catch {
    errors.targetUrl = raw ? "That isn't a valid URL." : "Enter the URL of the app to test.";
  }

  // "deep" is an interactive run with the deep engine: every interactive rule applies to it.
  const engine: RunEngine = input.mode === "deep" ? "deep" : "loop";
  const mode: RunMode | null =
    input.mode === "interactive" || input.mode === "deep" ? "interactive" : input.mode === "passive" ? "passive" : null;
  if (!mode) {
    errors.mode = "Choose passive, interactive or deep.";
  } else if (mode === "interactive" && targetUrl) {
    const verified = verifiedOrigins.some((origin) => sameOrigin(origin, targetUrl));
    if (!isDemoTarget(targetUrl) && !verified) {
      errors.mode = "Interactive tests run only on the demo shop and on domains you've verified. Verify yours in Settings → Domains (a DNS record or a file), or run a passive scan.";
    }
  }

  const focus = typeof input.focus === "string" ? input.focus.trim() : "";
  if (focus.length > MAX_FOCUS_LENGTH) {
    errors.focus = `Keep the focus under ${MAX_FOCUS_LENGTH} characters.`;
  }

  let engineModel: string | null = null;
  if (engine === "deep" && input.engineModel !== undefined && input.engineModel !== null && input.engineModel !== "") {
    if (typeof input.engineModel === "string" && (DEEP_MODELS as readonly string[]).includes(input.engineModel)) {
      engineModel = input.engineModel;
    } else {
      errors.engineModel = "Deep mode runs on Claude Sonnet 5.5 or Claude Opus 5.5.";
    }
  }

  if (Object.keys(errors).length > 0 || !mode) return { ok: false, errors };
  return { ok: true, value: { targetUrl, mode, focus: focus || null, engine, engineModel } };
}
