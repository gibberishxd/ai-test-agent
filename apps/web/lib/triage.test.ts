import { describe, expect, it } from "vitest";
import { compareRuns, parseTriageInput, reportedBugs } from "./triage";

const bug = (fingerprint: string | null, fields: Record<string, unknown> = {}) => ({
  id: fingerprint ?? "x",
  fingerprint,
  title: `Bug ${fingerprint}`,
  severity: "high",
  pageUrl: "https://shop.test/",
  status: "confirmed",
  suppressed: false,
  ...fields,
});

describe("reportedBugs", () => {
  it("leaves out what verification dismissed and what triage suppressed", () => {
    expect(reportedBugs([bug("a"), bug("b", { status: "dismissed" }), bug("c", { suppressed: true })]).map((b) => b.fingerprint)).toEqual(["a"]);
  });
});

describe("compareRuns", () => {
  it("sorts the findings into new, still present and fixed", () => {
    const previous = [bug("a"), bug("b")];
    const current = [bug("b"), bug("c")];
    const result = compareRuns(previous, current);
    expect(result.new.map((b) => b.fingerprint)).toEqual(["c"]);
    expect(result.stillPresent.map((b) => b.fingerprint)).toEqual(["b"]);
    expect(result.fixed.map((b) => b.fingerprint)).toEqual(["a"]);
  });

  it("counts a finding suppressed or dismissed in the previous run as not reported then", () => {
    const result = compareRuns([bug("a", { status: "dismissed" })], [bug("a")]);
    expect(result.new.map((b) => b.fingerprint)).toEqual(["a"]);
    expect(result.fixed).toEqual([]);
  });

  it("treats everything as new when there is no previous run, and an unfingerprinted bug as new", () => {
    expect(compareRuns(null, [bug("a"), bug(null)]).new).toHaveLength(2);
    expect(compareRuns([bug(null)], [bug(null)]).fixed).toEqual([]);
  });
});

describe("parseTriageInput", () => {
  it("accepts the three decisions with an optional comment", () => {
    expect(parseTriageInput({ state: "false_positive", comment: "  the total is right: 2 × $12  " })).toEqual({
      ok: true,
      value: { state: "false_positive", comment: "the total is right: 2 × $12" },
    });
    expect(parseTriageInput({ state: "wont_fix" })).toEqual({ ok: true, value: { state: "wont_fix", comment: null } });
    expect(parseTriageInput({ state: "ignore" })).toMatchObject({ ok: false });
  });
});
