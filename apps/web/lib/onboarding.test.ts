import { describe, expect, it } from "vitest";
import { onboardingSteps } from "./onboarding";

const fresh = { verifiedDomains: 0, usableModels: 0, runs: 0, finishedRunId: null };

describe("getting started (run 5, K5)", () => {
  it("a new workspace has its workspace step done and points at the next thing to do", () => {
    const steps = onboardingSteps(fresh);
    expect(steps.map((s) => [s.key, s.done])).toEqual([
      ["workspace", true],
      ["target", false],
      ["model", false],
      ["run", false],
      ["report", false],
    ]);
    expect(steps.find((s) => s.key === "target")?.href).toBe("/settings#domains");
  });

  it("the demo shop counts as a target and the server's model as a model once a run started", () => {
    const steps = onboardingSteps({ ...fresh, runs: 1 });
    expect(steps.filter((s) => s.done).map((s) => s.key)).toEqual(["workspace", "target", "model", "run"]);
  });

  it("a verified domain and a tested model tick their steps before any run", () => {
    const steps = onboardingSteps({ ...fresh, verifiedDomains: 1, usableModels: 1 });
    expect(steps.filter((s) => s.done).map((s) => s.key)).toEqual(["workspace", "target", "model"]);
  });

  it("the report step links to the first finished run", () => {
    const report = onboardingSteps({ ...fresh, runs: 1, finishedRunId: "abc" }).find((s) => s.key === "report");
    expect(report).toMatchObject({ done: true, href: "/runs/abc" });
  });
});
