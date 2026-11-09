import { describe, expect, it } from "vitest";
import { addItem, applyDiscount, cartTotal, type CartItem } from "./cart";

const mug: CartItem = { productId: 1, name: "Mug", price: 12, quantity: 2 };

describe("cartTotal", () => {
  it("multiplies price by quantity", () => {
    expect(cartTotal([mug])).toBe(24);
  });

  it("is zero for an empty cart", () => {
    expect(cartTotal([])).toBe(0);
  });

  it("ignores quantity when bug 5 is on", () => {
    expect(cartTotal([mug], { ignoreQuantity: true })).toBe(12);
  });
});

describe("applyDiscount", () => {
  it("takes 10% off once", () => {
    expect(applyDiscount(100, 10, 1)).toBe(90);
  });

  it("compounds when applied twice (bug 7)", () => {
    expect(applyDiscount(100, 10, 2)).toBe(81);
  });
});

describe("addItem", () => {
  it("adds a new product", () => {
    expect(addItem([], mug)).toEqual([mug]);
  });

  it("increases quantity for a product already in the cart", () => {
    expect(addItem([mug], { ...mug, quantity: 1 })[0].quantity).toBe(3);
  });
});
