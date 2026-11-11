/** The CI example script (examples/ci/ata-run.mjs): its decisions, without network calls. */
import { describe, expect, it } from "vitest";
// @ts-expect-error: a plain .mjs script without type declarations
import { failsAt, parseArgs, summarize } from "../../../examples/ci/ata-run.mjs";

describe("examples/ci/ata-run.mjs", () => {
  it("reads its options from flags, with safe defaults", () => {
    expect(parseArgs(["https://staging.example.com"])).toEqual({
      targetUrl: "https://staging.example.com",
      mode: "passive",
      failOn: "high",
      junit: null,
      timeoutMinutes: 30,
      maxSteps: null,
      maxMinutes: null,
      focus: null,
    });
    expect(parseArgs(["https://x.test", "--mode", "interactive", "--fail-on", "medium", "--junit", "out.xml", "--max-steps", "20"])).toMatchObject({
      mode: "interactive",
      failOn: "medium",
      junit: "out.xml",
      maxSteps: 20,
    });
  });

  it("fails the build when a bug at or above the threshold was found", () => {
    const counts = { critical: 0, high: 0, medium: 2, low: 5 };
    expect(failsAt(counts, "high")).toBe(false);
    expect(failsAt(counts, "medium")).toBe(true);
    expect(failsAt({ ...counts, critical: 1 }, "high")).toBe(true);
    expect(failsAt(counts, "none")).toBe(false);
  });

  it("prints a short summary with the worst bugs first", () => {
    const text = summarize({
      run: { status: "done", target_url: "https://x.test/", duration_s: 300, links: { dashboard: "https://app/runs/1" } },
      counts: { critical: 0, high: 1, medium: 0, low: 1 },
      bugs: [
        { severity: "low", title: "Image without alt text", page_url: "https://x.test/" },
        { severity: "high", title: "Checkout accepts an invalid email", page_url: "https://x.test/checkout" },
      ],
    });
    expect(text.indexOf("Checkout accepts")).toBeLessThan(text.indexOf("Image without"));
    expect(text).toContain("1 high");
    expect(text).toContain("https://app/runs/1");
  });
});
