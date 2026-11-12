import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { OnboardingStep } from "@/lib/onboarding";

/** The way from sign-up to the first report, with what is done (run 5, K5). */
export function GettingStarted({ steps }: { steps: OnboardingStep[] }) {
  const done = steps.filter((s) => s.done).length;
  const next = steps.find((s) => !s.done);
  return (
    <Card data-testid="getting-started">
      <CardHeader>
        <CardTitle className="text-lg">Getting started</CardTitle>
        <CardDescription>
          {done} of {steps.length} done. {next ? `Next: ${next.title.toLowerCase()}.` : "You're all set."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-3">
          {steps.map((step) => (
            <li key={step.key} className="flex gap-3" data-done={step.done}>
              {step.done ? (
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" aria-label="done" />
              ) : (
                <Circle className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-label="to do" />
              )}
              <div className="grid gap-0.5">
                <span className={step.done ? "font-medium" : "font-medium text-foreground"}>
                  {step.href && (!step.done || step.key === "report") ? (
                    <Link href={step.href} className="underline-offset-4 hover:underline">
                      {step.title}
                    </Link>
                  ) : (
                    step.title
                  )}
                </span>
                <span className="text-sm text-muted-foreground">{step.detail}</span>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
