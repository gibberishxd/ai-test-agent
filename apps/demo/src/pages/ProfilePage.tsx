import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { bug } from "../bugs";
import { formatPrice } from "../products";
import { useStore } from "../store";
import { usePageTitle } from "../usePageTitle";

type Order = { id: number; date: string; total: number };

export function ProfilePage() {
  usePageTitle("Profile");
  const { session, updateName } = useStore();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [ordersError, setOrdersError] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    // Bug 2 lives on the server side: in the buggy build /api/profile returns 500 (vite.config.ts).
    fetch("/api/profile")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<{ orders: Order[] }>;
      })
      .then((data) => setOrders(data.orders))
      .catch(() => setOrdersError(true));
  }, []);

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Bug 8: the save button does nothing: no update, no message, no error.
    if (bug(8)) return;
    updateName(String(new FormData(event.currentTarget).get("name") ?? ""));
    setSaved(true);
  };

  return (
    <>
      <h1>Profile</h1>
      {session ? (
        <form className="form" onSubmit={save}>
          <div className="field">
            <label htmlFor="name">Display name</label>
            <input id="name" name="name" defaultValue={session.name} />
          </div>
          <p className="muted">Email: {session.email}</p>
          <button type="submit" className="button">
            Save changes
          </button>
          {saved && <p role="status">Profile saved.</p>}
        </form>
      ) : (
        <p>
          You're browsing as a guest. <Link to="/login">Log in</Link> to edit your profile.
        </p>
      )}

      <h2>Recent orders</h2>
      {ordersError && <p className="error">We couldn't load your orders. Try again later.</p>}
      {!ordersError && orders === null && <p className="muted">Loading orders…</p>}
      {orders && (
        <ul>
          {orders.map((order) => (
            <li key={order.id}>
              #{order.id} · {order.date} · {formatPrice(order.total)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
