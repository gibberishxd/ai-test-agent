"use client";

import { Radio } from "lucide-react";
import { useState } from "react";
import { describeStep } from "@/components/step-timeline";
import { Button } from "@/components/ui/button";
import { fileUrl } from "@/lib/file-url";
import { boxOf, currentFrame, frames, outlineStyle, viewportOf } from "@/lib/live-pane";
import type { StepView } from "@/lib/serialize";
import { cn } from "@/lib/utils";

type Props = { steps: StepView[]; live: boolean; filesToken?: string | null };

/**
 * Watch the agent work: the screenshot it looked at, the element it chose outlined, what it
 * did and why. Follows the newest step while the run is live; the filmstrip below picks an
 * earlier one. Fed by the run page's polling, so it updates every 1.5 s.
 */
export function LivePane({ steps, live, filesToken = null }: Props) {
  const [picked, setPicked] = useState<number | null>(null);
  const all = frames(steps);
  const frame = currentFrame(steps, picked);
  if (!frame?.screenshot) return null;

  const outline = outlineStyle(boxOf(frame), viewportOf(frame));
  const position = all.findIndex((step) => step.index === frame.index) + 1;
  const following = picked === null || frame.index === all.at(-1)?.index;

  return (
    <section className="grid gap-3" aria-labelledby="live-pane-heading" data-testid="live-pane">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="live-pane-heading" className="flex items-center gap-2 text-lg font-semibold">
          {live && following && <Radio className="size-4 text-red-600" aria-label="Live" />}
          {live ? "Live browser" : "Browser replay"}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span data-testid="live-pane-counter">
            Step {position} of {all.length}
          </span>
          {!following && (
            <Button size="sm" variant="outline" onClick={() => setPicked(null)}>
              {live ? "Follow live" : "Latest step"}
            </Button>
          )}
        </div>
      </div>

      <figure className="grid gap-2">
        <div className="relative overflow-hidden rounded-xl border bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element -- served by our own API route */}
          <img
            src={fileUrl(frame.screenshot, filesToken)}
            alt={`What the agent saw at step ${position}: ${frame.url ?? ""}`}
            className="block h-auto w-full"
          />
          {outline && (
            <div
              className="pointer-events-none absolute rounded-sm border-2 border-red-600 shadow-[0_0_0_9999px_rgb(0_0_0/0.12)]"
              style={outline}
              data-testid="live-pane-outline"
              aria-hidden
            />
          )}
        </div>
        <figcaption className="grid gap-0.5 text-sm">
          <span className="font-medium">{describeStep(frame)}</span>
          {frame.reasoning && <span className="text-muted-foreground">{frame.reasoning}</span>}
          {frame.blocked && frame.blockReason && (
            <span className="text-amber-700 dark:text-amber-400">Blocked: {frame.blockReason}</span>
          )}
        </figcaption>
      </figure>

      {all.length > 1 && (
        <ol className="flex gap-2 overflow-x-auto pb-1" aria-label="Earlier steps">
          {all.map((step, i) => (
            <li key={step.index} className="shrink-0">
              <button
                type="button"
                onClick={() => setPicked(step.index)}
                aria-label={`Step ${i + 1}: ${describeStep(step)}`}
                aria-current={step.index === frame.index ? "step" : undefined}
                className={cn(
                  "block overflow-hidden rounded-md border-2 border-transparent",
                  step.index === frame.index && "border-primary",
                )}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- served by our own API route */}
                <img
                  src={fileUrl(step.screenshot!, filesToken)}
                  alt=""
                  className="h-14 w-24 object-cover object-top"
                  loading="lazy"
                />
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
