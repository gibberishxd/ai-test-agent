import { cartTotal, type CartItem } from "./cart";

// Placeholder shop. Phase 2 grows this into product list, cart, checkout, login and profile.
const items: CartItem[] = [
  { name: "Coffee mug", price: 12, quantity: 2 },
  { name: "Notebook", price: 8, quantity: 1 },
];

export function App() {
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>
      <h1>Demo Shop</h1>
      <ul>
        {items.map((item) => (
          <li key={item.name}>
            {item.name} × {item.quantity}: ${item.price * item.quantity}
          </li>
        ))}
      </ul>
      <p>
        <strong>Total: ${cartTotal(items)}</strong>
      </p>
    </main>
  );
}
