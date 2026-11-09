import { createContext, useContext, useState, type ReactNode } from "react";
import { bug } from "./bugs";
import { addItem, type CartItem } from "./cart";

/** Fake auth: one demo account. Never a real credential. */
export const DEMO_ACCOUNT = { email: "demo@example.com", password: "password123", name: "Demo User" };

export type Session = { email: string; name: string };

const SESSION_KEY = "demo-shop-session";

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

type Store = {
  cart: CartItem[];
  addToCart: (item: CartItem) => void;
  clearCart: () => void;
  session: Session | null;
  login: (email: string, password: string) => "ok" | "unknown-email" | "wrong-password";
  logout: () => void;
  updateName: (name: string) => void;
};

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<CartItem[]>([]);
  const [session, setSession] = useState<Session | null>(loadSession);

  const saveSession = (next: Session) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    setSession(next);
  };

  const store: Store = {
    cart,
    addToCart: (item) => setCart((items) => addItem(items, item)),
    clearCart: () => setCart([]),
    session,
    login: (email, password) => {
      if (email.trim().toLowerCase() !== DEMO_ACCOUNT.email) return "unknown-email";
      if (password !== DEMO_ACCOUNT.password) return "wrong-password";
      saveSession({ email: DEMO_ACCOUNT.email, name: DEMO_ACCOUNT.name });
      return "ok";
    },
    logout: () => {
      setSession(null);
      // Bug 11: the stored session isn't removed, so a page refresh logs the user back in.
      if (!bug(11)) localStorage.removeItem(SESSION_KEY);
    },
    updateName: (name) => {
      if (session) saveSession({ ...session, name });
    },
  };

  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
}

export function useStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useStore must be used inside StoreProvider");
  return store;
}
