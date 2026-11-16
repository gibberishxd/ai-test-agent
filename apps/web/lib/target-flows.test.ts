import { describe, expect, it } from "vitest";
import { MAX_FLOWS, parseFlowInput } from "./target-flows";

describe("parseFlowInput (run 7, M4)", () => {
  it("accepts a name and a journey in plain language", () => {
    expect(parseFlowInput({ name: " Checkout ", goal: " Add an item to the cart and place the order. " })).toEqual({
      ok: true,
      value: { name: "Checkout", goal: "Add an item to the cart and place the order." },
    });
  });

  it("needs both, within limits", () => {
    const missing = parseFlowInput({ name: "", goal: "" });
    expect(missing.ok).toBe(false);
    if (!missing.ok) expect(Object.keys(missing.errors).sort()).toEqual(["goal", "name"]);
    expect(parseFlowInput({ name: "x".repeat(101), goal: "g" }).ok).toBe(false);
    expect(parseFlowInput({ name: "n", goal: "g".repeat(2001) }).ok).toBe(false);
    expect(MAX_FLOWS).toBe(10);
  });
});
