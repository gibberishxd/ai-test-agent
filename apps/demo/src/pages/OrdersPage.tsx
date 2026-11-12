import { Link, Navigate, useParams } from "react-router";
import { ORDERS, orderDetails } from "../orders";
import { formatPrice } from "../products";
import { useStore } from "../store";
import { usePageTitle } from "../usePageTitle";

/** Only for a signed-in user: anyone else is sent to the login page and back here after. */
function useSignedIn(path: string) {
  const { session } = useStore();
  return session ? null : <Navigate to={`/login?next=${encodeURIComponent(path)}`} replace />;
}

export function OrdersPage() {
  usePageTitle("My orders");
  const redirect = useSignedIn("/orders");
  if (redirect) return redirect;
  return (
    <>
      <h1>My orders</h1>
      <ul className="orders">
        {ORDERS.map((o) => (
          <li key={o.id}>
            <Link to={`/orders/${o.id}`}>Order #{o.id}</Link> · {o.date} · {o.status} · {formatPrice(o.total)}
          </li>
        ))}
      </ul>
    </>
  );
}

export function OrderPage() {
  const { id } = useParams();
  usePageTitle(`Order #${id}`);
  const redirect = useSignedIn(`/orders/${id}`);
  if (redirect) return redirect;
  const order = orderDetails(Number(id));
  if (!order) return <h1>Order not found</h1>;
  return (
    <>
      <h1>Order #{order.id}</h1>
      <p className="muted">
        Placed {order.date} · {order.status}
      </p>
      <table className="order-lines">
        <thead>
          <tr>
            <th>Item</th>
            <th>Quantity</th>
            <th>Price</th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((line) => (
            <tr key={line.name}>
              <td>{line.name}</td>
              <td>{line.quantity}</td>
              <td>{formatPrice(line.price * line.quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Total: <strong>{formatPrice(order.total)}</strong>
      </p>
      <Link to="/orders">Back to my orders</Link>
    </>
  );
}
