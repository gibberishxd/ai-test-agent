import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { RunView } from "@/components/run-view";
import { serializeRun } from "@/lib/serialize";
import { getSharedRun } from "@/lib/share";

export const metadata: Metadata = { title: "Shared report", robots: { index: false } };

/** A read-only report anyone with the link can open. Revoking the link makes this a 404. */
export default async function SharedReportPage(props: PageProps<"/share/[token]">) {
  await connection();
  const { token } = await props.params;
  const run = await getSharedRun(token);
  if (!run) notFound();
  return (
    <main className="mx-auto grid max-w-4xl gap-4 px-4 py-10">
      <p className="w-fit rounded-full border px-3 py-1 text-sm text-muted-foreground">
        Shared report · read-only
      </p>
      <RunView initial={serializeRun(run)} readOnly />
    </main>
  );
}
