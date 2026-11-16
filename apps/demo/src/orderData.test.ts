import { describe, expect, it } from "vitest";
import { ORDERS } from "./orders";
import { profileOrders } from "./orderData";

// Run 7, benchmark v2: the profile's "Recent orders" listed two orders (#10231, #10457) that
// "My orders" never showed. Both now come from the same list, in both builds.
describe("recent orders on the profile", () => {
  it("are the orders on My orders: same ids, dates and totals, newest first", () => {
    const recent = profileOrders();
    expect(recent.length).toBeGreaterThan(0);
    for (const order of recent) {
      const mine = ORDERS.find((o) => o.id === order.id);
      expect(mine).toBeDefined();
      expect([order.date, order.total]).toEqual([mine!.date, mine!.total]);
    }
    expect(recent.map((o) => o.date)).toEqual([...recent.map((o) => o.date)].sort().reverse());
  });
});
