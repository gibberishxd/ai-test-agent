"use client";

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { flowStatus } from "@/lib/flow-status";
import type { FlowView } from "@/lib/target-flows";

type Draft = { name: string; goal: string };
const EMPTY: Draft = { name: "", goal: "" };

/**
 * A target's critical flows (run 7, M4): journeys in plain language, covered first on every run.
 * Shows each one's last result and whether it has a saved script (replayed without a model).
 */
export function FlowEditor({ targetId, flows, canEdit, max }: { targetId: string; flows: FlowView[]; canEdit: boolean; max: number }) {
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [errors, setErrors] = useState<Partial<Draft>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const open = (flow: FlowView | null) => {
    setEditing(flow ? flow.id : "new");
    setDraft(flow ? { name: flow.name, goal: flow.goal } : EMPTY);
    setErrors({});
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("save");
    const isNew = editing === "new";
    const response = await fetch(isNew ? `/api/targets/${targetId}/flows` : `/api/flows/${editing}`, {
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
    toast.success(isNew ? "Flow added. The next run completes it and saves its script." : "Flow saved.");
    router.refresh();
  };

  const remove = async (flow: FlowView) => {
    setBusy(flow.id);
    const response = await fetch(`/api/flows/${flow.id}`, { method: "DELETE" });
    setBusy(null);
    if (!response.ok) return toast.error("Couldn't delete the flow.");
    toast.success("Flow deleted.");
    router.refresh();
  };

  const form = (
    <form onSubmit={save} className="grid gap-3 rounded-xl border p-4" data-testid="flow-form">
      <div className="grid gap-1.5">
        <Label htmlFor="flow-name">Name</Label>
        <Input id="flow-name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Checkout" aria-invalid={Boolean(errors.name)} />
        {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="flow-goal">The journey, as a user would do it</Label>
        <Textarea
          id="flow-goal"
          rows={3}
          value={draft.goal}
          onChange={(e) => setDraft({ ...draft, goal: e.target.value })}
          placeholder="Add a product to the cart, go to the cart, check out with the test details and place the order."
          aria-invalid={Boolean(errors.goal)}
        />
        {errors.goal && <p className="text-sm text-destructive">{errors.goal}</p>}
        <p className="text-xs text-muted-foreground">Changing the wording makes the agent learn the journey again on the next run.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy === "save"}>
          {busy === "save" && <Loader2 className="animate-spin" />} Save flow
        </Button>
        <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
          Cancel
        </Button>
      </div>
    </form>
  );

  return (
    <div className="grid gap-4">
      {flows.length === 0 && editing !== "new" && (
        <p className="text-sm text-muted-foreground">No critical flows yet. Add the journeys that must never break; every run checks them first.</p>
      )}
      <ul className="grid gap-3" data-testid="flows">
        {flows.map((flow) =>
          editing === flow.id ? (
            <li key={flow.id}>{form}</li>
          ) : (
            <li key={flow.id} className="grid gap-2 rounded-xl border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 truncate font-medium">{flow.name}</span>
                <span className="flex flex-wrap items-center gap-2">
                  <Badge variant={flowStatus(flow.lastStatus).good === false ? "destructive" : "secondary"}>{flowStatus(flow.lastStatus).label}</Badge>
                  <Badge variant="outline">{flow.scriptSteps === null ? "No script yet" : `Script: ${flow.scriptSteps} step${flow.scriptSteps === 1 ? "" : "s"}`}</Badge>
                  {canEdit && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => open(flow)} aria-label={`Edit ${flow.name}`}>
                        <Pencil />
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy === flow.id} onClick={() => remove(flow)} aria-label={`Delete ${flow.name}`}>
                        {busy === flow.id ? <Loader2 className="animate-spin" /> : <Trash2 />}
                      </Button>
                    </>
                  )}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">{flow.goal}</p>
              {flow.lastRunId && (
                <Link href={`/runs/${flow.lastRunId}`} className="w-fit text-xs text-muted-foreground hover:underline">
                  Last run →
                </Link>
              )}
            </li>
          ),
        )}
      </ul>
      {canEdit && flows.length < max && (editing === "new" ? form : (
        <Button variant="outline" className="w-fit" onClick={() => open(null)}>
          <Plus /> Add a flow
        </Button>
      ))}
    </div>
  );
}
