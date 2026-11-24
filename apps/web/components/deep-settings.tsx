"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = { steps: number | null; minutes: number | null; defaults: { steps: number; minutes: number }; canEdit: boolean };

/** The workspace's deep-mode limits (run 9). Empty = the product default. */
export function DeepSettings({ steps, minutes, defaults, canEdit }: Props) {
  const [stepsValue, setSteps] = useState(steps === null ? "" : String(steps));
  const [minutesValue, setMinutes] = useState(minutes === null ? "" : String(minutes));
  const [errors, setErrors] = useState<{ steps?: string; minutes?: string }>({});
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const response = await fetch("/api/deep-limits", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: stepsValue, minutes: minutesValue }),
    });
    const data = await response.json().catch(() => ({}));
    setSaving(false);
    if (response.ok) {
      setErrors({});
      toast.success("Deep mode limits saved.");
    } else {
      setErrors(data.errors ?? {});
    }
  };

  return (
    <form onSubmit={save} className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
      <div className="grid gap-2">
        <Label htmlFor="deep-steps">Steps per run</Label>
        <Input id="deep-steps" inputMode="numeric" placeholder={String(defaults.steps)} value={stepsValue}
          onChange={(e) => setSteps(e.target.value)} disabled={!canEdit} aria-invalid={Boolean(errors.steps)} />
        {errors.steps && <p className="text-sm text-destructive">{errors.steps}</p>}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="deep-minutes">Minutes per run</Label>
        <Input id="deep-minutes" inputMode="numeric" placeholder={String(defaults.minutes)} value={minutesValue}
          onChange={(e) => setMinutes(e.target.value)} disabled={!canEdit} aria-invalid={Boolean(errors.minutes)} />
        {errors.minutes && <p className="text-sm text-destructive">{errors.minutes}</p>}
      </div>
      {canEdit && (
        <Button type="submit" disabled={saving} className="w-full sm:w-fit">
          Save
        </Button>
      )}
    </form>
  );
}
