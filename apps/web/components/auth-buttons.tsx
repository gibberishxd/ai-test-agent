"use client";

import { Loader2, LogOut, Mail, UserRound } from "lucide-react";
import { signIn, signOut } from "next-auth/react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = { github: boolean; email: boolean; demo: boolean };

export function SignInOptions({ github, email, demo }: Props) {
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const sendLink = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("email");
    await signIn("email", { email: address, callbackUrl: "/dashboard" });
  };

  if (!github && !email && !demo) {
    return (
      <p className="text-sm text-muted-foreground">
        No sign-in method is configured. Set AUTH_GITHUB_ID / AUTH_GITHUB_SECRET or EMAIL_SERVER /
        EMAIL_FROM in .env (see the README).
      </p>
    );
  }

  return (
    <div className="grid gap-4">
      {github && (
        <Button size="lg" variant="outline" onClick={() => { setBusy("github"); signIn("github", { callbackUrl: "/dashboard" }); }} disabled={busy !== null}>
          {busy === "github" ? <Loader2 className="animate-spin" /> : <GitHubMark />} Continue with GitHub
        </Button>
      )}
      {email && (
        <form onSubmit={sendLink} className="grid gap-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required placeholder="you@company.com" value={address} onChange={(e) => setAddress(e.target.value)} />
          <Button type="submit" size="lg" disabled={busy !== null}>
            {busy === "email" ? <Loader2 className="animate-spin" /> : <Mail />} Email me a sign-in link
          </Button>
        </form>
      )}
      {demo && (
        <div className="grid gap-2 border-t pt-4">
          <Button size="lg" variant="secondary" onClick={() => { setBusy("demo"); signIn("demo", { callbackUrl: "/dashboard" }); }} disabled={busy !== null}>
            {busy === "demo" ? <Loader2 className="animate-spin" /> : <UserRound />} Sign in as demo user
          </Button>
          <p className="text-xs text-muted-foreground">Development only. Not available in production.</p>
        </div>
      )}
    </div>
  );
}

export function SignOutButton() {
  return (
    <Button variant="ghost" size="sm" onClick={() => signOut({ callbackUrl: "/" })} aria-label="Sign out">
      <LogOut /> <span className="hidden sm:inline">Sign out</span>
    </Button>
  );
}

/** GitHub's mark (lucide-react no longer ships brand logos). */
function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
