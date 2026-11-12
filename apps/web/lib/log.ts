/**
 * Structured logs (run 4, J6): one JSON object per line on stdout, so a log collector can filter
 * by level, run or workspace. Values under secret-looking keys are never written.
 */
type Level = "debug" | "info" | "warn" | "error";
const SECRET_KEY = /pass|secret|token|key|authorization|cookie/i;

export function logLine(level: Level, message: string, context: Record<string, unknown> = {}, now = new Date()): string {
  const safe = Object.fromEntries(Object.entries(context).map(([k, v]) => [k, SECRET_KEY.test(k) ? "[redacted]" : v]));
  return JSON.stringify({ time: now.toISOString(), level, message, ...safe });
}

export function log(level: Level, message: string, context: Record<string, unknown> = {}): void {
  if (level === "debug" && process.env.LOG_LEVEL !== "debug") return;
  (level === "error" ? console.error : console.log)(logLine(level, message, context));
}
