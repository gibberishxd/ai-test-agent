/**
 * The demo account's orders: the one list behind both "My orders" (orders.ts) and the profile's
 * "Recent orders" (served by the fake API in vite.config.ts). No planted-bug switch here: the
 * dev server's config imports this file. Run 7 (benchmark v2): the profile used to list two
 * orders that "My orders" never showed.
 */
export type OrderLine = { name: string; quantity: number; price: number };
export type Order = { id: number; date: string; status: string; items: OrderLine[]; total: number };

function order(id: number, date: string, status: string, items: OrderLine[]): Order {
  return { id, date, status, items, total: items.reduce((sum, i) => sum + i.price * i.quantity, 0) };
}

export const ORDERS: Order[] = [
  order(1001, "2026-09-14", "Delivered", [{ name: "Ceramic Mug", quantity: 2, price: 12 }]),
  order(1002, "2026-10-02", "Delivered", [
    { name: "Notebook", quantity: 1, price: 6 },
    { name: "Desk Lamp", quantity: 1, price: 45 },
  ]),
  order(1003, "2026-11-01", "Shipped", [{ name: "Canvas Tote", quantity: 3, price: 18 }]),
];

/** What the profile API returns as recent orders: id, date and total, newest first. */
export function profileOrders(): { id: number; date: string; total: number }[] {
  return [...ORDERS]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map(({ id, date, total }) => ({ id, date, total }));
}
