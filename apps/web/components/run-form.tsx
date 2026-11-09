"use client";

import { Loader2, Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type { FieldErrors } from "@/lib/targets";

type Props = { demoUrl: string };

export async function startRun(body: { targetUrl: string; mode: string; focus?: string }) {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (response.ok) return { id: data.id as string };
  return { errors: (data.errors ?? { targetUrl: "Something went wrong. Try again." }) as FieldErrors };
}

export function RunForm({ demoUrl }: Props) {
  const router = useRouter();
  const [targetUrl, setTargetUrl] = useState("");
  const [mode, setMode] = useState("passive");
  const [focus, setFocus] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    const result = await startRun({ targetUrl, mode, focus });
    if ("id" in result) {
      router.push(`/runs/${result.id}`);
      return;
    }
    setErrors(result.errors);
    setSubmitting(false);
  };

  return (
    <form onSubmit={submit} noValidate className="grid gap-5">
      <div className="grid gap-2">
        <Label htmlFor="target-url">URL to test</Label>
        <Input
          id="target-url"
          name="targetUrl"
          type="url"
          inputMode="url"
          placeholder="https://your-app.com"
          value={targetUrl}
          onChange={(event) => setTargetUrl(event.target.value)}
          aria-invalid={Boolean(errors.targetUrl)}
          aria-describedby={errors.targetUrl ? "target-url-error" : undefined}
        />
        {errors.targetUrl ? (
          <p id="target-url-error" className="text-sm text-destructive">
            {errors.targetUrl}
          </p>
        ) : (
          <button
            type="button"
            className="w-fit text-left text-sm text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => setTargetUrl(demoUrl)}
          >
            No app handy? Use the demo shop ({demoUrl})
          </button>
        )}
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium">Mode</legend>
        <RadioGroup value={mode} onValueChange={setMode} className="grid gap-3 sm:grid-cols-2">
          <ModeOption
            value="passive"
            title="Passive scan"
            text="Visits pages and follows links. Never types, submits or clicks buttons. Safe on any public site."
          />
          <ModeOption
            value="interactive"
            title="Interactive test"
            text="Also fills forms and walks through flows. Only on the demo shop and domains you've verified."
          />
        </RadioGroup>
        {errors.mode && <p className="text-sm text-destructive">{errors.mode}</p>}
      </fieldset>

      <div className="grid gap-2">
        <Label htmlFor="focus">
          Focus <span className="font-normal text-muted-foreground">(optional)</span>
        </Label>
        <Textarea
          id="focus"
          name="focus"
          rows={2}
          placeholder="e.g. test checkout, or test sign-up"
          value={focus}
          onChange={(event) => setFocus(event.target.value)}
        />
        {errors.focus && <p className="text-sm text-destructive">{errors.focus}</p>}
      </div>

      <Button type="submit" size="lg" disabled={submitting} className="w-full sm:w-fit">
        {submitting ? <Loader2 className="animate-spin" /> : <Play />}
        Start test
      </Button>
    </form>
  );
}

function ModeOption({ value, title, text }: { value: string; title: string; text: string }) {
  const id = `mode-${value}`;
  return (
    <Label
      htmlFor={id}
      className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/5"
    >
      <RadioGroupItem id={id} value={value} className="mt-0.5" />
      <span className="grid gap-1">
        <span className="font-medium">{title}</span>
        <span className="text-sm text-muted-foreground">{text}</span>
      </span>
    </Label>
  );
}
