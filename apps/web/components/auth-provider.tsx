"use client";

import { SessionProvider } from "next-auth/react";
import type { ReactNode } from "react";

/** Lets client components call signIn / signOut. */
export function AuthProvider({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
