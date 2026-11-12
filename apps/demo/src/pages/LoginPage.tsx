import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { bug } from "../bugs";
import { DEMO_ACCOUNT, useStore } from "../store";
import { usePageTitle } from "../usePageTitle";

type FieldName = "email" | "password";
type LoginError = { field: FieldName; message: string } | null;

export function LoginPage() {
  usePageTitle("Log in");
  const { login } = useStore();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // Back to the page that asked for a login; only paths in this shop (no open redirect).
  const next = params.get("next");
  const after = next && next.startsWith("/") && !next.startsWith("//") ? next : "/profile";
  const [error, setError] = useState<LoginError>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = login(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
    if (result === "ok") {
      navigate(after);
    } else if (result === "unknown-email") {
      setError({ field: "email", message: "No account with that email." });
    } else {
      // Bug 12: the wrong-password message is shown under the email field.
      setError({ field: bug(12) ? "email" : "password", message: "Incorrect password." });
    }
  };

  const errorFor = (field: FieldName) =>
    error?.field === field ? (
      <p id={`${field}-error`} className="error" role="alert">
        {error.message}
      </p>
    ) : null;

  return (
    <>
      <h1>Log in</h1>
      <p className="muted">
        Demo account: {DEMO_ACCOUNT.email} / {DEMO_ACCOUNT.password}
      </p>
      <form className="form" onSubmit={submit} noValidate>
        <div className="field" data-testid="email-field">
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="username" />
          {errorFor("email")}
        </div>
        <div className="field" data-testid="password-field">
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" />
          {errorFor("password")}
        </div>
        <button type="submit" className="button">
          Log in
        </button>
      </form>
    </>
  );
}
