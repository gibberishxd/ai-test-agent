import { describe, expect, it, vi } from "vitest";
import { logLine } from "./log";

describe("logLine", () => {
  it("is one JSON object per line with level, message, time and context ids", () => {
    const line = JSON.parse(logLine("info", "run started", { runId: "r1", workspaceId: "w1" }, new Date("2026-11-11T10:00:00Z")));
    expect(line).toEqual({ time: "2026-11-11T10:00:00.000Z", level: "info", message: "run started", runId: "r1", workspaceId: "w1" });
  });

  it("never writes keys that look secret", () => {
    const line = JSON.parse(logLine("warn", "x", { apiKey: "ata_abc", password: "p", token: "t", runId: "r1" }));
    expect(line).toEqual(expect.objectContaining({ apiKey: "[redacted]", password: "[redacted]", token: "[redacted]", runId: "r1" }));
    vi.restoreAllMocks();
  });
});
