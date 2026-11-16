"use client";

import { Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Add a target (run 7): an app to test, by URL. Only its origin is kept. */
export function TargetForm() {
  const router = useRouter();
  const [form, setForm] = useState({ url: "", name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const response = await fetch("/api/targets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(data.errors?.url ?? data.error ?? "Couldn't add the target.");
      return;
    }
    setError(null);
    setForm({ url: "", name: "" });
    toast.success("Target added.");
    router.push(`/targets/${data.target.id}`);
  };

  return (
    <form onSubmit={add} className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-end">
      <div className="grid gap-1.5">
        <Label htmlFor="target-url">App URL</Label>
        <Input id="target-url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://staging.example.com" aria-invalid={Boolean(error)} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="target-name">Name (optional)</Label>
        <Input id="target-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Staging" />
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Plus />} Add target
      </Button>
      {error && <p className="text-sm text-destructive sm:col-span-3">{error}</p>}
    </form>
  );
}
