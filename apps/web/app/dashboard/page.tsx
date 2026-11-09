import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { RunForm } from "@/components/run-form";
import { RunHistory } from "@/components/run-history";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { listRuns } from "@/lib/runs";
import { demoUrl } from "@/lib/targets";
import { currentWorkspaceId } from "@/lib/workspace";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  await connection();
  const runs = await listRuns(await currentWorkspaceId(), 5);

  return (
    <main className="mx-auto grid max-w-6xl gap-10 px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Test a web app</CardTitle>
          <CardDescription>
            Paste a URL. The agent explores it like a QA tester and reports what it finds, with
            evidence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RunForm demoUrl={demoUrl()} />
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
