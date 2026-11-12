import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { GettingStarted } from "@/components/getting-started";
import { RunForm } from "@/components/run-form";
import { RunHistory } from "@/components/run-history";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { listModelConfigs } from "@/lib/model-configs";
import { onboardingState, onboardingSteps } from "@/lib/onboarding";
import { listRuns } from "@/lib/runs";
import { demoUrl } from "@/lib/targets";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  await connection();
  const context = await currentContext();
  const runs = await listRuns(context.workspaceId, 5);
  const models = context.signedIn ? await listModelConfigs(context.workspaceId) : [];
  // A new team sees the way to its first report until that report exists.
  const steps = context.signedIn ? onboardingSteps(await onboardingState(context.workspaceId)) : null;
  const showSteps = steps !== null && !steps.every((s) => s.done);

  return (
    <main className="mx-auto grid max-w-6xl gap-10 px-4 py-10">
      {showSteps && <GettingStarted steps={steps} />}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Test a web app</CardTitle>
          <CardDescription>
            Paste a URL. The agent explores it like a QA tester and reports what it finds, with
            evidence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RunForm
            demoUrl={demoUrl()}
            models={models.map((m) => ({ id: m.id, label: m.label, model: m.model, usable: m.usable, isDefault: m.isDefault }))}
          />
        </CardContent>
      </Card>

      <section className="grid gap-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Recent runs</h2>
          {runs.length > 0 && (
            <Link href="/runs" className="text-sm text-muted-foreground hover:underline">
              See all runs
            </Link>
          )}
        </div>
        <RunHistory runs={runs} />
      </section>
    </main>
  );
}
