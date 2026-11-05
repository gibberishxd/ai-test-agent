import { describe, expect, it } from "vitest";
import { cartTotal } from "./cart";

describe("cartTotal", () => {
  it("multiplies price by quantity", () => {
    expect(cartTotal([{ name: "Mug", price: 12, quantity: 2 }])).toBe(24);
  });

  it("is zero for an empty cart", () => {
    expect(cartTotal([])).toBe(0);
  });
});
