import { describe, expect, it } from "vitest";
import { flowStatus } from "./flow-status";

describe("flowStatus (run 7)", () => {
  it("says how each journey went, and whether the model was needed", () => {
    expect(flowStatus("replayed")).toEqual({ label: "Passed by replay (no model)", good: true });
    expect(flowStatus("failed").good).toBe(false);
    expect(flowStatus(null)).toEqual({ label: "Not run yet", good: null });
    expect(flowStatus("mystery").label).toBe("mystery");
  });
});
