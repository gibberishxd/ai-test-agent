import { Link } from "react-router";
import { usePageTitle } from "../usePageTitle";

/** Shown for unknown routes. The data-testid lets the checker spot SPA "404s" (HTTP status is 200). */
export function NotFound() {
  usePageTitle("Page not found");
  return (
    <div data-testid="not-found">
      <h1>Page not found</h1>
      <p>
        That page doesn't exist. <Link to="/">Back to the shop</Link>
      </p>
    </div>
  );
}
