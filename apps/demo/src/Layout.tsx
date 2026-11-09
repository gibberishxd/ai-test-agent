import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router";
import { bug } from "./bugs";
import { useStore } from "./store";

export function Layout({ children }: { children: ReactNode }) {
  const { cart, session, logout } = useStore();
  const [searchOpen, setSearchOpen] = useState(false);
  const count = cart.reduce((n, item) => n + item.quantity, 0);

  return (
    <>
      <header className="header">
        <Link to="/" className="brand">
          Demo Shop
        </Link>
        <nav aria-label="Main">
          <NavLink to="/">Shop</NavLink>
          <NavLink to="/cart">Cart ({count})</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          {session ? (
            <button type="button" className="link-button" onClick={logout}>
              Log out
            </button>
          ) : (
            <NavLink to="/login">Log in</NavLink>
          )}
          {/* Bug 4 (part 2): an icon-only button with no accessible name. */}
          <button
            type="button"
            className="icon-button"
            data-testid="search-button"
            aria-label={bug(4) ? undefined : "Search"}
            onClick={() => setSearchOpen((open) => !open)}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" fill="none" />
              <line x1="16" y1="16" x2="21" y2="21" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </nav>
      </header>
      {searchOpen && <SearchBar />}
      <main className="main">{children}</main>
      <footer className="footer">
        <p>Demo Shop is a practice target for AI Test Agent. Nothing here is for sale.</p>
        {/* Bug 3: the footer links to a page that doesn't exist (the server returns 404). */}
        <a href={bug(3) ? "/return-policy" : "/returns"}>Returns policy</a>
      </footer>
    </>
  );
}

function SearchBar() {
  const [query, setQuery] = useState("");
  useEffect(() => {
    document.dispatchEvent(new CustomEvent("demo-search", { detail: query }));
  }, [query]);
  return (
    <div className="search">
      <label htmlFor="search-input">Search products</label>
      <input
        id="search-input"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
    </div>
  );
}
