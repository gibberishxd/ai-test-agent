import { bug } from "./bugs";

/** The demo account's past orders: a page only signed-in users can reach (run 4). */
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

/** The order to show for an id from the URL. */
export function orderDetails(id: number): Order | null {
  const index = ORDERS.findIndex((o) => o.id === id);
  if (index < 0) return null;
  // Bug 13: an off-by-one shows the next order (and the first one after the last).
  return bug(13) ? ORDERS[(index + 1) % ORDERS.length] : ORDERS[index];
}
