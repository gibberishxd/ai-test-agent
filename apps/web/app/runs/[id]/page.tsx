import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { RunView } from "@/components/run-view";
import { hostOf } from "@/lib/format";
import { getRun } from "@/lib/runs";
import { serializeRun } from "@/lib/serialize";
import { currentWorkspaceId } from "@/lib/workspace";

export async function generateMetadata(props: PageProps<"/runs/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  const run = await getRun(await currentWorkspaceId(), id);
  return { title: run ? `Run on ${hostOf(run.targetUrl)}` : "Run not found" };
}

export default async function RunPage(props: PageProps<"/runs/[id]">) {
  await connection();
  const { id } = await props.params;
  const run = await getRun(await currentWorkspaceId(), id);
  if (!run) notFound();
  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <RunView initial={serializeRun(run)} />
    </main>
  );
}
