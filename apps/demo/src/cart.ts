export type CartItem = { name: string; price: number; quantity: number };

/** Cart total in the same currency unit as the prices. Phase 2 plants a bug here on purpose. */
export function cartTotal(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}
