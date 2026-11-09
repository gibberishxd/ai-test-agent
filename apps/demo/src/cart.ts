export type CartItem = { productId: number; name: string; price: number; quantity: number };

export type TotalOptions = {
  /** Bug 5 when true: the total adds each line's price once, ignoring the quantity. */
  ignoreQuantity?: boolean;
};

/** Cart subtotal in dollars. */
export function cartTotal(items: CartItem[], options: TotalOptions = {}): number {
  return items.reduce(
    (sum, item) => sum + item.price * (options.ignoreQuantity ? 1 : item.quantity),
    0,
  );
}

/** Apply a percentage discount `times` times (bug 7 lets it apply more than once). */
export function applyDiscount(amount: number, percent: number, times: number): number {
  let result = amount;
  for (let i = 0; i < times; i++) result -= result * (percent / 100);
  return Math.round(result * 100) / 100;
}

/** Add a product to the cart, or increase its quantity if it's already there. */
export function addItem(items: CartItem[], item: CartItem): CartItem[] {
  const existing = items.find((i) => i.productId === item.productId);
  if (!existing) return [...items, item];
  return items.map((i) =>
    i.productId === item.productId ? { ...i, quantity: i.quantity + item.quantity } : i,
  );
}
