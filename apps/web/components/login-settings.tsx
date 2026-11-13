"use client";

import { CheckCircle2, KeyRound, Loader2, Plus, Trash2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LoginSetupView } from "@/lib/login-setups";

const EMPTY = {
  targetUrl: "",
  kind: "form",
  loginUrl: "",
  username: "",
  password: "",
  usernameSelector: "",
  passwordSelector: "",
  submitSelector: "",
  successSelector: "",
  storageState: "",
};
type Field = keyof typeof EMPTY;
type Errors = Partial<Record<Field | "selectors", string>>;

const POLL_MS = 1500;
const POLL_LIMIT = 40; // ~60 s: a sign-in that takes longer has failed anyway

/**
 * Sign-in setups: how the worker signs in to a site before the agent tests it. Use a TEST
 * account. The password (or recorded sign-in) is sent once, stored encrypted and never shown
 * again; Test sign-in asks the worker to sign in once and shows only "worked" or why not.
 */
export function LoginSettings({ setups }: { setups: LoginSetupView[] }) {
  const router = useRouter();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState<string | null>(null);
  const set = (field: Field) => (event: { target: { value: string } }) => setForm({ ...form, [field]: event.target.value });

  async function call(path: string, method: string, body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    return { response, data: await response.json().catch(() => ({})) };
  }

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("save");
    const { response, data } = await call("/api/login-setups", "POST", form);
    setBusy(null);
    if (!response.ok) {
      setErrors(data.errors ?? {});
      if (data.error) toast.error(data.error);
      return;
    }
    setForm(EMPTY);
    setErrors({});
    toast.success("Sign-in saved. Run Test sign-in to check it works.");
    router.refresh();
  };

  const testSignIn = async (setup: LoginSetupView) => {
    setBusy(setup.id);
    const { response, data } = await call(`/api/login-setups/${setup.id}/test`, "POST");
    if (!response.ok) {
      setBusy(null);
      return toast.error(data.error ?? "Couldn't start the test.");
    }
    for (let i = 0; i < POLL_LIMIT; i++) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      const { data: listed } = await call("/api/login-setups", "GET");
      const current = (listed.setups as LoginSetupView[] | undefined)?.find((s) => s.id === setup.id);
      if (current && !current.checking) {
        setBusy(null);
        if (current.lastCheck?.ok) toast.success(`Signed in: ${current.lastCheck.detail}`);
        else toast.error(current.lastCheck?.detail ?? "The sign-in failed.");
        router.refresh();
        return;
      }
    }
    setBusy(null);
    toast.error("No worker picked up the test. Is the worker running?");
  };

  const remove = async (setup: LoginSetupView) => {
    setBusy(setup.id + "delete");
    const { response, data } = await call(`/api/login-setups/${setup.id}`, "DELETE");
    setBusy(null);
    if (!response.ok) return toast.error(data.error ?? "Something went wrong.");
    toast.success("Sign-in setup deleted.");
    router.refresh();
  };

  return (
    <div className="grid gap-6">
      {setups.length > 0 && (
        <ul className="grid gap-3" data-testid="login-setup-list">
          {setups.map((setup) => (
            <li key={setup.id} className="grid gap-2 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium break-all">{setup.origin}</span>
                <CheckBadge setup={setup} />
              </div>
              <p className="text-sm break-all text-muted-foreground">
                {setup.kind === "form"
                  ? `Login form at ${setup.loginUrl} · ${setup.username} · password ${setup.passwordSaved ? "saved" : "missing"}`
                  : `Recorded sign-in ${setup.storageStateSaved ? "saved" : "missing"}`}
              </p>
              {setup.lastCheck && !setup.lastCheck.ok && <p className="text-sm text-destructive">{setup.lastCheck.detail}</p>}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => testSignIn(setup)}>
                  {busy === setup.id ? <Loader2 className="animate-spin" /> : <KeyRound />}
                  Test sign-in
                </Button>
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => remove(setup)}>
                  <Trash2 /> Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={save} noValidate className="grid gap-3 rounded-lg border p-4">
        <p className="font-medium">Add or replace a sign-in</p>
        <p className="text-sm text-muted-foreground">
          Use a test account, never a real person&apos;s. The agent is never told the password, can&apos;t log out,
          change the password or delete the account, and is signed in again if the session ends.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="login-target" label="Site" error={errors.targetUrl}>
            <Input id="login-target" value={form.targetUrl} onChange={set("targetUrl")} placeholder="https://staging.example.com" />
          </FormField>
          <FormField id="login-kind" label="How to sign in" error={errors.kind}>
            <select id="login-kind" value={form.kind} onChange={set("kind")} className="h-9 w-full min-w-0 truncate rounded-md border bg-transparent px-3 text-sm">
              <option value="form">Fill in the login form</option>
              <option value="storage_state">Use a recorded sign-in (SSO, two-factor)</option>
            </select>
          </FormField>
          {form.kind === "form" ? (
            <>
              <FormField id="login-url" label="Login page" error={errors.loginUrl}>
                <Input id="login-url" value={form.loginUrl} onChange={set("loginUrl")} placeholder="https://staging.example.com/login" />
              </FormField>
              <FormField id="login-username" label="Test account username or email" error={errors.username}>
                <Input id="login-username" autoComplete="off" value={form.username} onChange={set("username")} />
              </FormField>
              <FormField id="login-password" label="Password" error={errors.password}>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={set("password")}
                  placeholder="Stored encrypted, never shown again"
                />
              </FormField>
            </>
          ) : (
            <div className="sm:col-span-2">
              <FormField id="login-state" label="Recorded sign-in (Playwright storage state JSON)" error={errors.storageState}>
                <textarea
                  id="login-state"
                  value={form.storageState}
                  onChange={set("storageState")}
                  rows={4}
                  className="rounded-md border bg-transparent p-2 font-mono text-xs"
                  placeholder='{"cookies": [...], "origins": [...]}  (npx playwright codegen --save-storage=state.json)'
                />
              </FormField>
            </div>
          )}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">Selectors (optional: only if the fields aren&apos;t found)</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {form.kind === "form" && (
              <>
                <FormField id="sel-user" label="Username field">
                  <Input id="sel-user" value={form.usernameSelector} onChange={set("usernameSelector")} placeholder="#email" />
                </FormField>
                <FormField id="sel-pass" label="Password field">
                  <Input id="sel-pass" value={form.passwordSelector} onChange={set("passwordSelector")} placeholder="#password" />
                </FormField>
                <FormField id="sel-submit" label="Submit button">
                  <Input id="sel-submit" value={form.submitSelector} onChange={set("submitSelector")} placeholder="button[type=submit]" />
                </FormField>
              </>
            )}
            <FormField id="sel-success" label="Only shown when signed in" error={errors.selectors}>
              <Input id="sel-success" value={form.successSelector} onChange={set("successSelector")} placeholder="[data-testid=account-menu]" />
            </FormField>
          </div>
        </details>
        <Button type="submit" className="w-fit" disabled={busy !== null}>
          {busy === "save" ? <Loader2 className="animate-spin" /> : <Plus />} Save sign-in
        </Button>
      </form>
    </div>
  );
}

function CheckBadge({ setup }: { setup: LoginSetupView }) {
  if (setup.checking) return <Badge variant="outline">Testing…</Badge>;
  if (!setup.lastCheck) return <Badge variant="outline">Not tested</Badge>;
  return setup.lastCheck.ok ? (
    <Badge variant="outline" className="gap-1 text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 className="size-3" /> Signs in
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1 text-destructive">
      <XCircle className="size-3" /> Failed
    </Badge>
  );
}

function FormField({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
