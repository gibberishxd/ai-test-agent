import { useState } from "react";
import { Link } from "react-router";
import { bug } from "../bugs";
import { applyDiscount, cartTotal } from "../cart";
import { formatPrice } from "../products";
import { useStore } from "../store";
import { usePageTitle } from "../usePageTitle";

export const DISCOUNT_CODE = "SAVE10";
const DISCOUNT_PERCENT = 10;

export function CartPage() {
  usePageTitle("Cart");
  const { cart } = useStore();
  const [code, setCode] = useState("");
  const [timesApplied, setTimesApplied] = useState(0);
  const [codeError, setCodeError] = useState("");

  if (cart.length === 0) {
    return (
      <>
        <h1>Your cart</h1>
        <p>Your cart is empty.</p>
        <Link to="/" className="button">
          Browse products
        </Link>
      </>
    );
  }

  // Bug 5: the total ignores quantities.
  const subtotal = cartTotal(cart, { ignoreQuantity: bug(5) });
  const total = applyDiscount(subtotal, DISCOUNT_PERCENT, timesApplied);

  const apply = () => {
    if (code.trim().toUpperCase() !== DISCOUNT_CODE) {
      setCodeError("That code isn't valid.");
      return;
    }
    setCodeError("");
    // Bug 7: no guard against applying the code again, so a double click applies it twice.
    setTimesApplied((n) => (bug(7) ? n + 1 : 1));
  };

  return (
    <>
      <h1>Your cart</h1>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col">Quantity</th>
            <th scope="col">Price</th>
          </tr>
        </thead>
        <tbody>
          {cart.map((item) => (
            <tr key={item.productId}>
              <td>{item.name}</td>
              <td>{item.quantity}</td>
              <td>{formatPrice(item.price * item.quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="row">
        <label htmlFor="discount">Discount code</label>
        <input id="discount" value={code} onChange={(event) => setCode(event.target.value)} />
        <button type="button" className="button secondary" onClick={apply}>
          Apply
        </button>
      </div>
      {codeError && <p className="error">{codeError}</p>}
      {timesApplied > 0 && (
        <p data-testid="discount-line">
          Discount {DISCOUNT_CODE} applied ({DISCOUNT_PERCENT}% off){timesApplied > 1 ? ` ×${timesApplied}` : ""}
        </p>
      )}

      <p className="total">
        Total: <strong data-testid="cart-total">{formatPrice(total)}</strong>
      </p>
      <Link to="/checkout" className="button">
        Go to checkout
      </Link>
    </>
  );
}
