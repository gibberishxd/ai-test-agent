"use client";

import { Copy, KeyRound, Loader2, Pause, Play, Plus, Trash2, Webhook } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiKeyView } from "@/lib/api-keys";
import type { WebhookView } from "@/lib/webhooks";

/**
 * Run tests from CI: API keys (shown once, then only their prefix) and webhooks (a signed POST
 * when a run finishes; the signing secret is shown once). docs/API.md has copy-paste examples.
 */
export function IntegrationSettings({ keys, webhooks }: { keys: ApiKeyView[]; webhooks: WebhookView[] }) {
  const router = useRouter();
  const [keyName, setKeyName] = useState("");
  const [hookUrl, setHookUrl] = useState("");
  const [hookError, setHookError] = useState<string | null>(null);
  const [shown, setShown] = useState<{ label: string; value: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function call(path: string, method: string, body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    return { response, data: await response.json().catch(() => ({})) };
  }

  const createKey = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("key");
    const { response, data } = await call("/api/api-keys", "POST", { name: keyName });
    setBusy(null);
    if (!response.ok) return toast.error(data.error ?? "Couldn't create the key.");
    setKeyName("");
    setShown({ label: `API key “${data.apiKey.name}”`, value: data.key });
    router.refresh();
  };

  const createHook = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("hook");
    const { response, data } = await call("/api/webhooks", "POST", { url: hookUrl });
    setBusy(null);
    if (!response.ok) {
      setHookError(data.errors?.url ?? null);
      if (data.error) toast.error(data.error);
      return;
    }
    setHookUrl("");
    setHookError(null);
    setShown({ label: `Signing secret for ${data.webhook.url}`, value: data.secret });
    router.refresh();
  };

  const act = async (id: string, path: string, method: string, body: unknown, success: string) => {
    setBusy(id);
    const { response, data } = await call(path, method, body);
    setBusy(null);
    if (!response.ok) return toast.error(data.error ?? "Something went wrong.");
    toast.success(success);
    router.refresh();
  };

  return (
    <div className="grid gap-6">
      {shown && (
        <div className="grid gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3" role="status" data-testid="shown-once">
          <p className="text-sm font-medium">{shown.label}: copy it now. It won&apos;t be shown again.</p>
          <div className="flex gap-2">
            <code className="flex-1 overflow-x-auto rounded bg-background px-2 py-1.5 text-xs break-all">{shown.value}</code>
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigator.clipboard.writeText(shown.value).then(() => toast.success("Copied."))}
            >
              <Copy /> Copy
            </Button>
          </div>
          <Button size="sm" variant="ghost" className="w-fit" onClick={() => setShown(null)}>
            I&apos;ve saved it
          </Button>
        </div>
      )}

      <section className="grid gap-3">
        <h3 className="flex items-center gap-2 font-medium">
          <KeyRound className="size-4" /> API keys
        </h3>
        {keys.length > 0 && (
          <ul className="grid gap-2" data-testid="api-key-list">
            {keys.map((key) => (
              <li key={key.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
                <span className="font-medium">{key.name}</span>
                <code className="text-xs text-muted-foreground">{key.prefix}…</code>
                {key.revokedAt ? <Badge variant="outline">Revoked</Badge> : <Badge variant="outline">Active</Badge>}
                <span className="text-muted-foreground">
                  {key.lastUsedAt ? `last used ${new Date(key.lastUsedAt).toLocaleString()}` : "never used"}
                </span>
                {!key.revokedAt && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    disabled={busy !== null}
                    onClick={() => act(key.id, `/api/api-keys/${key.id}`, "DELETE", undefined, "Key revoked.")}
                  >
                    <Trash2 /> Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={createKey} className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor="key-name">Key name</Label>
            <Input id="key-name" value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="e.g. GitHub Actions" />
          </div>
          <Button type="submit" disabled={busy !== null}>
            {busy === "key" ? <Loader2 className="animate-spin" /> : <Plus />} Create key
          </Button>
        </form>
      </section>

      <section className="grid gap-3">
        <h3 className="flex items-center gap-2 font-medium">
          <Webhook className="size-4" /> Webhooks
        </h3>
        <p className="text-sm text-muted-foreground">
          When a run finishes we POST a signed <code>run.finished</code> event. Check the <code>X-ATA-Signature</code> header with
          your secret (docs/API.md). Failed deliveries are retried for about 3 hours.
        </p>
        {webhooks.map((hook) => (
          <div key={hook.id} className="grid gap-2 rounded-lg border p-3 text-sm" data-testid="webhook">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium break-all">{hook.url}</span>
              <Badge variant="outline">{hook.enabled ? "Active" : "Paused"}</Badge>
              <div className="ml-auto flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => act(hook.id, `/api/webhooks/${hook.id}`, "PATCH", { enabled: !hook.enabled }, hook.enabled ? "Paused." : "Resumed.")}
                >
                  {hook.enabled ? <Pause /> : <Play />} {hook.enabled ? "Pause" : "Resume"}
                </Button>
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => act(hook.id, `/api/webhooks/${hook.id}`, "DELETE", undefined, "Webhook deleted.")}>
                  <Trash2 /> Delete
                </Button>
              </div>
            </div>
            {hook.deliveries.length > 0 ? (
              <ul className="grid gap-1 text-xs text-muted-foreground">
                {hook.deliveries.map((d) => (
                  <li key={d.id}>
                    {new Date(d.createdAt).toLocaleString()} · {d.event} · {d.status}
                    {d.lastStatusCode ? ` · HTTP ${d.lastStatusCode}` : ""} · {d.attempts} attempt{d.attempts === 1 ? "" : "s"}
                    {d.lastError && d.status !== "delivered" ? ` · ${d.lastError}` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No deliveries yet.</p>
            )}
          </div>
        ))}
        <form onSubmit={createHook} className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor="hook-url">Endpoint URL</Label>
            <Input id="hook-url" value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} placeholder="https://ci.example.com/hooks/ata" className="w-80 max-w-full" />
            {hookError && <p className="text-sm text-destructive">{hookError}</p>}
          </div>
          <Button type="submit" disabled={busy !== null}>
            {busy === "hook" ? <Loader2 className="animate-spin" /> : <Plus />} Add webhook
          </Button>
        </form>
      </section>
    </div>
  );
}
