import { describe, expect, it } from "vitest";
import { ORDERS, orderDetails } from "./orders";

// Vitest runs in "test" mode, so bug(n) is on: this pins the planted bug 13 (verify-bugs checks
// both builds in a browser).
describe("orders", () => {
  it("lists past orders whose totals add up", () => {
    expect(ORDERS.map((o) => o.id)).toEqual([1001, 1002, 1003]);
    for (const order of ORDERS) {
      expect(order.total).toBe(order.items.reduce((sum, i) => sum + i.price * i.quantity, 0));
    }
  });

  it("has the planted bug: opening an order shows the next one", () => {
    expect(orderDetails(1001)?.id).toBe(1002);
    expect(orderDetails(1003)?.id).toBe(1001); // wraps around
    expect(orderDetails(9999)).toBeNull();
  });
});
