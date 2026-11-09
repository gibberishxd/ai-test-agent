import { describe, expect, it } from "vitest";
import { toGitHubIssue, toJira, type ExportableBug } from "./export";

const bug: ExportableBug = {
  title: "GET /api/profile fails with HTTP 500",
  severity: "high",
  category: "network",
  pageUrl: "http://localhost:5173/profile",
  expected: "The fetch request succeeds.",
  actual: "GET /api/profile returned HTTP 500.",
  reproSteps: ["Open http://localhost:5173/profile", "Open the Network tab"],
  evidence: {
    failed_requests: [
      { method: "GET", url: "http://localhost:5173/api/profile", status: 500, failure: null },
    ],
  },
};
const context = { runUrl: "http://localhost:3000/runs/abc", targetUrl: "http://localhost:5173" };

describe("toGitHubIssue", () => {
  const text = toGitHubIssue(bug, context);

  it("numbers the repro steps", () => {
    expect(text).toContain("1. Open http://localhost:5173/profile\n2. Open the Network tab");
  });

  it("includes expected, actual and evidence", () => {
    expect(text).toContain("### Expected\nThe fetch request succeeds.");
    expect(text).toContain("GET http://localhost:5173/api/profile → 500");
  });

  it("links back to the report", () => {
    expect(text).toContain("[full report](http://localhost:3000/runs/abc)");
  });
});

describe("toJira", () => {
  const text = toJira(bug, context);

  it("uses Jira wiki markup", () => {
    expect(text.startsWith("h3. GET /api/profile fails with HTTP 500")).toBe(true);
    expect(text).toContain("# Open the Network tab");
    expect(text).toContain("{noformat}");
    expect(text).toContain("[Full report|http://localhost:3000/runs/abc]");
  });

  it("leaves out the evidence section when there is none", () => {
    expect(toJira({ ...bug, evidence: {} }, context)).not.toContain("{noformat}");
  });
});
