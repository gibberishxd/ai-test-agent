"use client";

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { SpecView } from "@/lib/target-specs";

type Draft = { title: string; body: string };
const EMPTY: Draft = { title: "", body: "" };

/**
 * A target's specs (run 7, M3): add, edit and delete requirements as Markdown or plain text.
 * The worker splits them at their headings and embeds them before the next run on the target.
 */
export function SpecEditor({ targetId, specs, canEdit }: { targetId: string; specs: SpecView[]; canEdit: boolean }) {
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null); // a spec id, "new", or null
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [errors, setErrors] = useState<Partial<Draft>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const open = (spec: SpecView | null) => {
    setEditing(spec ? spec.id : "new");
    setDraft(spec ? { title: spec.title, body: spec.body } : EMPTY);
    setErrors({});
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("save");
    const isNew = editing === "new";
    const response = await fetch(isNew ? `/api/targets/${targetId}/specs` : `/api/specs/${editing}`, {
      method: isNew ? "POST" : "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setErrors(data.errors ?? {});
      if (data.error) toast.error(data.error);
      return;
    }
    setEditing(null);
    toast.success(isNew ? "Spec added. It's used from the next run on." : "Spec saved. It's used from the next run on.");
    router.refresh();
  };

  const remove = async (spec: SpecView) => {
    setBusy(spec.id);
    const response = await fetch(`/api/specs/${spec.id}`, { method: "DELETE" });
    setBusy(null);
    if (!response.ok) return toast.error("Couldn't delete the spec.");
    toast.success("Spec deleted.");
    router.refresh();
  };

  const form = (
    <form onSubmit={save} className="grid gap-3 rounded-xl border p-4" data-testid="spec-form">
      <div className="grid gap-1.5">
        <Label htmlFor="spec-title">Title</Label>
        <Input id="spec-title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Checkout" aria-invalid={Boolean(errors.title)} />
        {errors.title && <p className="text-sm text-destructive">{errors.title}</p>}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="spec-body">Requirements (Markdown or plain text)</Label>
        <Textarea
          id="spec-body"
          rows={12}
          className="font-mono text-xs"
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          placeholder={"## Discount codes\nAs a shopper I want to use a discount code so that I pay less.\n- Given a valid code, when I apply it, then the total drops by its amount once."}
          aria-invalid={Boolean(errors.body)}
        />
        {errors.body && <p className="text-sm text-destructive">{errors.body}</p>}
        <p className="text-xs text-muted-foreground">Headings split it into parts; the agent sees the parts that match the page it&apos;s on. Write what should happen, as you would for a QA engineer.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy === "save"}>
          {busy === "save" && <Loader2 className="animate-spin" />} Save spec
        </Button>
        <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
          Cancel
        </Button>
      </div>
    </form>
  );

  return (
    <div className="grid gap-4">
      {specs.length === 0 && editing !== "new" && (
        <p className="text-sm text-muted-foreground">No specs yet. Add your requirements, and runs on this target test against them.</p>
      )}
      <ul className="grid gap-3" data-testid="specs">
        {specs.map((spec) =>
          editing === spec.id ? (
            <li key={spec.id}>{form}</li>
          ) : (
            <li key={spec.id} className="grid gap-2 rounded-xl border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 truncate font-medium">{spec.title}</span>
                <span className="flex items-center gap-2">
                  <Badge variant={spec.status === "ready" ? "secondary" : "outline"} title={spec.status === "ready" ? "Embedded" : "Embedded before the next run"}>
                    {spec.status === "ready" ? `${spec.chunks} part${spec.chunks === 1 ? "" : "s"}` : "Waiting for the next run"}
                  </Badge>
                  {canEdit && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => open(spec)} aria-label={`Edit ${spec.title}`}>
                        <Pencil />
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy === spec.id} onClick={() => remove(spec)} aria-label={`Delete ${spec.title}`}>
                        {busy === spec.id ? <Loader2 className="animate-spin" /> : <Trash2 />}
                      </Button>
                    </>
                  )}
                </span>
              </div>
              <pre className="max-h-40 overflow-auto rounded-lg bg-muted/50 p-3 font-mono text-xs whitespace-pre-wrap break-words">{spec.body}</pre>
            </li>
          ),
        )}
      </ul>
      {canEdit && (editing === "new" ? form : (
        <Button variant="outline" className="w-fit" onClick={() => open(null)}>
          <Plus /> Add a spec
        </Button>
      ))}
    </div>
  );
}
