import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { bug } from "../bugs";
import { useStore } from "../store";
import { usePageTitle } from "../usePageTitle";

/** The only card number the demo accepts (a well-known test number, never a real card). */
export const TEST_CARD = "4242424242424242";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  // Bug 6: the buggy check only makes sure the field isn't empty.
  return bug(6) ? email.trim().length > 0 : EMAIL_PATTERN.test(email.trim());
}

type Errors = Partial<Record<"name" | "email" | "card", string>>;

export function CheckoutPage() {
  usePageTitle("Checkout");
  const { cart, clearCart } = useStore();
  const [errors, setErrors] = useState<Errors>({});
  const [orderNumber, setOrderNumber] = useState<number | null>(null);

  if (orderNumber) {
    return (
      <>
        <h1>Order confirmed</h1>
        <p role="status">Thanks! Your order #{orderNumber} is on its way (not really: this is a demo).</p>
        <Link to="/">Back to the shop</Link>
      </>
    );
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "");
    const email = String(form.get("email") ?? "");
    const card = String(form.get("card") ?? "").replace(/\s/g, "");

    const next: Errors = {};
    if (!name.trim()) next.name = "Enter your name.";
    if (!isValidEmail(email)) next.email = "Enter a valid email address.";
    if (card !== TEST_CARD) next.card = "Use the test card 4242 4242 4242 4242.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    clearCart();
    setOrderNumber(10_000 + Math.floor(Math.random() * 90_000));
  };

  return (
    <>
      <h1>Checkout</h1>
      {cart.length === 0 && <p className="muted">Your cart is empty, but you can still try the form.</p>}
      {/* noValidate: our own validation decides, not the browser's built-in email check. */}
      <form className="form" onSubmit={submit} noValidate>
        <Field id="name" label="Full name" error={errors.name} autoComplete="name" />
        <Field id="email" label="Email" type="email" error={errors.email} autoComplete="email" />
        <Field id="card" label="Card number" error={errors.card} autoComplete="cc-number" />
        <button type="submit" className="button">
          Place order
        </button>
      </form>
    </>
  );
}

function Field(props: { id: string; label: string; error?: string; type?: string; autoComplete?: string }) {
  const errorId = `${props.id}-error`;
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <input
        id={props.id}
        name={props.id}
        type={props.type ?? "text"}
        autoComplete={props.autoComplete}
        aria-invalid={props.error ? true : undefined}
        aria-describedby={props.error ? errorId : undefined}
      />
      {props.error && (
        <p id={errorId} className="error">
          {props.error}
        </p>
      )}
    </div>
  );
}
