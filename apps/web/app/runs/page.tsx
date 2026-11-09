import type { Metadata } from "next";
import { connection } from "next/server";
import { RunHistory } from "@/components/run-history";
import { listRuns } from "@/lib/runs";
import { currentWorkspaceId } from "@/lib/workspace";

export const metadata: Metadata = { title: "Runs" };

export default async function RunsPage() {
  await connection();
  const runs = await listRuns(await currentWorkspaceId(), 100);
  return (
    <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Run history</h1>
        <p className="text-muted-foreground">Every test run in this workspace, newest first.</p>
      </div>
      <RunHistory runs={runs} />
    </main>
  );
}
