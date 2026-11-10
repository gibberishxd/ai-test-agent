"use client";

import { CheckCircle2, Loader2, Plus, PlugZap, Star, Trash2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ModelConfigView } from "@/lib/model-configs";

const EMPTY = { label: "", provider: "openai-compat", baseUrl: "", model: "", apiKey: "", inputPrice: "", outputPrice: "" };
type Field = keyof typeof EMPTY;

/**
 * Bring any model: add an OpenAI-compatible endpoint or an Anthropic key, test it, pick a
 * default. A pasted key is sent once, stored encrypted, and only shown again as "•••• last4".
 */
export function ModelSettings({ models }: { models: ModelConfigView[] }) {
  const router = useRouter();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
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

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("add");
    const { response, data } = await call("/api/models", "POST", form);
    setBusy(null);
    if (!response.ok) {
      setErrors(data.errors ?? {});
      if (data.error) toast.error(data.error);
      return;
    }
    setForm(EMPTY);
    setErrors({});
    toast.success("Model added. Run Test connection before using it.");
    router.refresh();
  };

  const act = async (id: string, path: string, method: string, body?: unknown, success?: string) => {
    setBusy(id + path + method);
    const { response, data } = await call(path, method, body);
    setBusy(null);
    if (!response.ok) return toast.error(data.error ?? "Something went wrong.");
    if (path.endsWith("/test")) {
      const model = data.model as ModelConfigView;
      if (model.usable) toast.success("Connected: answers, calls tools, reads images.");
      else toast.error(model.probe?.error ?? "The test failed.");
    } else if (success) toast.success(success);
    router.refresh();
  };

  const replaceKey = (model: ModelConfigView) => {
    const apiKey = window.prompt(`New API key for ${model.label}`);
    if (apiKey) void act(model.id, `/api/models/${model.id}`, "PATCH", { apiKey }, "Key replaced. Test the connection again.");
  };

  return (
    <div className="grid gap-6">
      {models.length > 0 && (
        <ul className="grid gap-3" data-testid="model-list">
          {models.map((model) => (
            <li key={model.id} className="grid gap-2 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{model.label}</span>
                {model.isDefault && <Badge>Default</Badge>}
                {model.probe === null ? (
                  <Badge variant="outline">Not tested</Badge>
                ) : model.usable ? (
                  <Badge variant="outline" className="gap-1 text-emerald-700 dark:text-emerald-400">
                    <CheckCircle2 className="size-3" /> Ready
                  </Badge>
                ) : (
                  <Badge variant="outline" className="gap-1 text-destructive">
                    <XCircle className="size-3" /> Failed
                  </Badge>
                )}
              </div>
              <p className="text-sm break-all text-muted-foreground">
                {model.provider === "claude" ? "Anthropic" : model.baseUrl} · {model.model}
                {model.keyHint ? ` · key ${model.keyHint}` : " · no key"}
              </p>
              {model.probe && !model.usable && model.probe.error && (
                <p className="text-sm text-destructive">{model.probe.error}</p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => act(model.id, `/api/models/${model.id}/test`, "POST")}>
                  {busy === model.id + `/api/models/${model.id}/test` + "POST" ? <Loader2 className="animate-spin" /> : <PlugZap />}
                  Test connection
                </Button>
                {!model.isDefault && (
                  <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => act(model.id, `/api/models/${model.id}`, "PATCH", { isDefault: true }, "Default model set.")}>
                    <Star /> Make default
                  </Button>
                )}
                <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => replaceKey(model)}>
                  Replace key
                </Button>
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => act(model.id, `/api/models/${model.id}`, "DELETE", undefined, "Model deleted.")}>
                  <Trash2 /> Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} noValidate className="grid gap-3 rounded-lg border p-4">
        <p className="font-medium">Add a model</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="model-label" label="Name" error={errors.label}>
            <Input id="model-label" value={form.label} onChange={set("label")} placeholder="e.g. OpenRouter Gemini" />
          </FormField>
          <FormField id="model-provider" label="Provider" error={errors.provider}>
            <select
              id="model-provider"
              value={form.provider}
              onChange={set("provider")}
              className="h-9 rounded-md border bg-transparent px-3 text-sm"
            >
              <option value="openai-compat">OpenAI-compatible (OpenAI, Gemini, OpenRouter, Groq, local…)</option>
              <option value="claude">Anthropic (Claude)</option>
            </select>
          </FormField>
          {form.provider === "openai-compat" && (
            <FormField id="model-base-url" label="Base URL" error={errors.baseUrl}>
              <Input id="model-base-url" value={form.baseUrl} onChange={set("baseUrl")} placeholder="https://api.openai.com/v1" />
            </FormField>
          )}
          <FormField id="model-id" label="Model" error={errors.model}>
            <Input id="model-id" value={form.model} onChange={set("model")} placeholder="e.g. gpt-5-mini" />
          </FormField>
          <FormField id="model-key" label="API key" error={errors.apiKey}>
            <Input id="model-key" type="password" autoComplete="off" value={form.apiKey} onChange={set("apiKey")} placeholder="Stored encrypted, never shown again" />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField id="model-in" label="$ / M input" error={errors.inputPrice}>
              <Input id="model-in" inputMode="decimal" value={form.inputPrice} onChange={set("inputPrice")} placeholder="0" />
            </FormField>
            <FormField id="model-out" label="$ / M output" error={errors.outputPrice}>
              <Input id="model-out" inputMode="decimal" value={form.outputPrice} onChange={set("outputPrice")} placeholder="0" />
            </FormField>
          </div>
        </div>
        <Button type="submit" className="w-fit" disabled={busy !== null}>
          {busy === "add" ? <Loader2 className="animate-spin" /> : <Plus />} Add model
        </Button>
      </form>
    </div>
  );
}

function FormField({ id, label, error, children }: { id: string; label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
