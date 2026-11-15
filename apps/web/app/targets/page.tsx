import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Crosshair } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { TargetForm } from "@/components/target-form";
import { can } from "@/lib/roles";
import { listTargets } from "@/lib/target-specs";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Targets" };

export default async function TargetsPage() {
  const context = await currentContext();
  if (!context.signedIn) redirect("/signin");
  const targets = await listTargets(context.workspaceId);
  const manage = can(context.role ?? null, "targets.manage");

  return (
    <main className="mx-auto grid max-w-4xl grid-cols-[minmax(0,1fr)] gap-8 px-4 py-10">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">Targets</h1>
        <p className="text-sm text-muted-foreground">
          The apps you test. Give each one your specs (requirements to test against) and its critical flows (journeys checked on every run).
        </p>
      </div>
      {manage && <TargetForm />}
      {targets.length === 0 ? (
        <EmptyState icon={Crosshair} title="No targets yet">
          Add your app&apos;s URL to give the agent your specs and critical flows. Runs on that address use them automatically.
        </EmptyState>
      ) : (
        <ul className="grid gap-3" data-testid="targets">
          {targets.map((target) => (
            <li key={target.id}>
              <Link href={`/targets/${target.id}`} className="flex flex-wrap items-baseline justify-between gap-2 rounded-xl border p-4 hover:bg-muted/50">
                <span className="min-w-0 truncate font-medium">{target.name ?? target.origin}</span>
                <span className="text-sm text-muted-foreground">
                  {target.name && <span className="mr-3 font-mono text-xs">{target.origin}</span>}
                  {target.specs} spec{target.specs === 1 ? "" : "s"} · {target.flows} flow{target.flows === 1 ? "" : "s"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
