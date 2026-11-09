import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BUG_REPORT_FIELDS, SEVERITIES } from "./types";

// Written by the worker: `uv run python -m worker.contracts` (a worker test keeps it current).
const schema = JSON.parse(readFileSync(new URL("./schema.json", import.meta.url), "utf8"));

describe("BugReport contract", () => {
  const bug = schema.BugReport;

  it("has the same fields as the worker's model", () => {
    expect(Object.keys(BUG_REPORT_FIELDS).sort()).toEqual(Object.keys(bug.properties).sort());
  });

  it("agrees on which fields are required", () => {
    const required = Object.entries(BUG_REPORT_FIELDS)
      .filter(([, kind]) => kind === "required")
      .map(([name]) => name)
      .sort();
    expect(required).toEqual([...bug.required].sort());
  });

  it("agrees on the severities", () => {
    expect(SEVERITIES).toEqual(bug.properties.severity.enum);
  });
});
