import { describe, expect, it } from "vitest";
import { apiReport, junitReport, parseApiRunInput } from "./api-v1";

describe("parseApiRunInput", () => {
  it("maps the API's snake_case body to a run, defaulting to a passive scan", () => {
    expect(parseApiRunInput({ target_url: "https://staging.example.com" })).toEqual({
      ok: true,
      value: { body: { targetUrl: "https://staging.example.com", mode: "passive", focus: null, modelConfigId: null }, maxSteps: null, maxSeconds: null },
    });
    const full = parseApiRunInput({
      target_url: "https://staging.example.com",
      mode: "interactive",
      focus: "checkout",
      model_id: "6f1c3f8e-1b1a-4f55-9a77-2d4f7d0a1c11",
      max_steps: 25,
      max_minutes: 10,
    });
    expect(full).toMatchObject({ ok: true, value: { maxSteps: 25, maxSeconds: 600, body: { mode: "interactive", focus: "checkout" } } });
  });

  it("refuses budgets outside the limits and unknown fields' wrong types", () => {
    expect(parseApiRunInput({ target_url: "https://x.test", max_steps: 0 })).toMatchObject({ ok: false, errors: { max_steps: expect.any(String) } });
    expect(parseApiRunInput({ target_url: "https://x.test", max_minutes: 120 })).toMatchObject({ ok: false, errors: { max_minutes: expect.any(String) } });
    expect(parseApiRunInput({ target_url: 5 })).toMatchObject({ ok: false, errors: { target_url: expect.any(String) } });
  });
});

const run = {
  id: "11111111-2222-3333-4444-555555555555",
  targetUrl: "https://staging.example.com/",
  mode: "interactive",
  status: "done",
  costUsd: 0.12,
  createdAt: new Date("2026-11-11T10:00:00Z"),
  startedAt: new Date("2026-11-11T10:00:05Z"),
  finishedAt: new Date("2026-11-11T10:05:05Z"),
  pagesVisited: 4,
  bugs: [
    { id: "b1", title: 'Total <wrong> & "off"', severity: "high", category: "functional", pageUrl: "https://staging.example.com/cart", status: "confirmed", source: "agent", expected: "$24", actual: "$12", reproSteps: ["Open /cart"], dismissReason: null },
    { id: "b2", title: "Maybe a bug", severity: "low", category: "ux", pageUrl: "https://staging.example.com/", status: "dismissed", source: "agent", expected: null, actual: null, reproSteps: [], dismissReason: "replay: not shown" },
  ],
};

describe("apiReport", () => {
  it("lists what the run reports (not what verification dismissed) and counts by severity", () => {
    const report = apiReport(run);
    expect(report.bugs.map((b) => b.id)).toEqual(["b1"]);
    expect(report.counts).toEqual({ critical: 0, high: 1, medium: 0, low: 0 });
    expect(report.run).toMatchObject({ id: run.id, status: "done", duration_s: 300 });
  });
});

describe("junitReport", () => {
  it("is a JUnit suite with one failing case per bug, escaped", () => {
    const xml = junitReport(run);
    expect(xml).toContain('<testsuite name="AI Test Agent: https://staging.example.com/" tests="1" failures="1"');
    expect(xml).toContain("Total &lt;wrong&gt; &amp; &quot;off&quot;");
    expect(xml).toContain('<failure type="high"');
    expect(xml).not.toContain("Maybe a bug");
  });

  it("has one passing case when nothing was found, so CI shows the run", () => {
    const xml = junitReport({ ...run, bugs: [] });
    expect(xml).toContain('tests="1" failures="0"');
    expect(xml).toContain('<testcase name="No bugs found"');
  });
});
