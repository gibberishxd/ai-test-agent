import { bug } from "./bugs";
import { ORDERS, type Order } from "./orderData";

/** The demo account's past orders: a page only signed-in users can reach (run 4). The data is in
 * orderData.ts, shared with the profile API (vite.config.ts) since run 7. */
export { ORDERS };
export type { Order, OrderLine } from "./orderData";

/** The order to show for an id from the URL. */
export function orderDetails(id: number): Order | null {
  const index = ORDERS.findIndex((o) => o.id === id);
  if (index < 0) return null;
  // Bug 13: an off-by-one shows the next order (and the first one after the last).
  return bug(13) ? ORDERS[(index + 1) % ORDERS.length] : ORDERS[index];
}
