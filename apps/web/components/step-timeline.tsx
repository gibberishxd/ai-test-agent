import { fileUrl } from "@/lib/file-url";
import { Ban, Bot, Eye, Globe, MousePointerClick } from "lucide-react";
import type { StepView } from "@/lib/serialize";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Globe> = {
  visit: Globe,
  click: MousePointerClick,
  review_screenshot: Eye,
  verify_bug: Eye,
};

/** A step in plain words, for the timeline and the live browser pane. */
export function describeStep(step: StepView): string {
  const args = step.args;
  const element = args.element as { role?: string; name?: string } | null | undefined;
  const target = element?.name ? `${element.role ?? "element"} "${element.name}"` : "";
  switch (step.action) {
    case "visit":
      return `Visited ${step.url ?? ""}${args.status ? ` (HTTP ${args.status})` : ""}`;
    case "click":
      return `Clicked ${target || "an element"}`;
    case "double_click":
      return `Double-clicked ${target || "an element"}`;
    case "reload":
      return "Reloaded the page";
    case "set_viewport":
      return `Switched to the ${String(args.size ?? "")} screen`;
    case "note":
      return `Noted: ${String(args.text ?? "")}`;
    case "type":
      return `Typed "${String(args.text ?? "")}" into ${target || "a field"}`;
    case "select":
      return `Selected "${String(args.option ?? "")}" in ${target || "a dropdown"}`;
    case "navigate":
      return `Went to ${String(args.url ?? "")}`;
    case "go_back":
      return "Went back";
    case "scroll":
      return `Scrolled ${String(args.direction ?? "down")}`;
    case "take_screenshot":
      return "Took a screenshot";
    case "report_bug":
      return `Reported a bug: ${String(args.title ?? "")}`;
    case "finish":
      return "Finished exploring";
    case "review_screenshot":
      return "Reviewed screenshots for visual problems";
    case "verify_bug":
      return `Replayed a bug to verify it: ${String(args.bug ?? "")}`;
    case "dedupe":
      return "Merged duplicate bugs";
    default:
      return step.action;
  }
}

export function StepTimeline({ steps, filesToken = null }: { steps: StepView[]; filesToken?: string | null }) {
  return (
    <ol className="grid gap-3" data-testid="timeline">
      {steps.map((step) => {
        const Icon = step.blocked ? Ban : (ICONS[step.action] ?? Bot);
        const result = typeof step.args.result === "string" ? step.args.result : null;
        return (
          <li
            key={step.index}
            className={cn(
              "flex gap-3 rounded-lg border p-3",
              step.blocked && "border-amber-500/50 bg-amber-500/5",
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted",
                step.blocked && "bg-amber-500/15 text-amber-700 dark:text-amber-300",
              )}
            >
              <Icon className="size-4" />
            </span>
            <div className="grid min-w-0 flex-1 gap-1 text-sm">
              <p className="font-medium break-words">
                <span className="mr-2 text-muted-foreground tabular-nums">#{step.index + 1}</span>
                {describeStep(step)}
              </p>
              {step.reasoning && <p className="text-muted-foreground">{step.reasoning}</p>}
              {step.blocked && step.blockReason && (
                <p className="text-amber-700 dark:text-amber-300">Blocked: {step.blockReason}</p>
              )}
              {result && !step.blocked && result !== "ok" && (
                <p className="text-xs text-muted-foreground">{result}</p>
              )}
              {step.events.length > 0 && (
                <ul className="text-xs text-red-700 dark:text-red-300">
                  {step.events.slice(0, 3).map((event, i) => (
                    <li key={i} className="truncate">
                      {event.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {step.screenshot && (
              // eslint-disable-next-line @next/next/no-img-element -- served by our own API route
              <img
                src={fileUrl(step.screenshot, filesToken)}
                alt=""
                className="hidden h-16 w-24 shrink-0 rounded border object-cover object-top sm:block"
                loading="lazy"
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
