import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { FlowEditor } from "@/components/flow-editor";
import { SpecEditor } from "@/components/spec-editor";
import { can } from "@/lib/roles";
import { listFlows, MAX_FLOWS } from "@/lib/target-flows";
import { getTarget, listSpecs } from "@/lib/target-specs";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Target" };

const TABS = [
  { id: "specs", label: "Specs" },
  { id: "flows", label: "Flows" },
] as const;

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> };

/** One target (run 7): its specs (M3) and its critical flows (M4), as tabs. */
export default async function TargetPage({ params, searchParams }: Props) {
  const context = await currentContext();
  if (!context.signedIn) redirect("/signin");
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  const target = await getTarget(context.workspaceId, id);
  if (!target) notFound();
  const active = tab === "flows" ? "flows" : "specs";
  const canEdit = can(context.role ?? null, "targets.manage");
  const [specs, flows] = await Promise.all([
    active === "specs" ? listSpecs(context.workspaceId, id) : Promise.resolve([]),
    active === "flows" ? listFlows(context.workspaceId, id) : Promise.resolve([]),
  ]);

  return (
    <main className="mx-auto grid max-w-4xl grid-cols-[minmax(0,1fr)] gap-6 px-4 py-10">
      <div className="grid gap-1">
        <Link href="/targets" className="w-fit text-sm text-muted-foreground hover:underline">
          ← Targets
        </Link>
        <h1 className="truncate text-2xl font-semibold">{target.name ?? target.origin}</h1>
        <p className="font-mono text-xs text-muted-foreground">{target.origin}</p>
      </div>
      <nav aria-label="Target" className="flex gap-1 border-b">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={`/targets/${id}?tab=${t.id}`}
            aria-current={active === t.id ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${active === t.id ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {t.label} <span className="text-muted-foreground">({t.id === "specs" ? target.specs : target.flows})</span>
          </Link>
        ))}
      </nav>
      {active === "specs" ? (
        <section className="grid gap-3" aria-label="Specs">
          <p className="text-sm text-muted-foreground">
            Your requirements for this app: user stories and acceptance criteria. On each page the agent sees the parts that match it and tests against
            them; a finding that breaks one says which.
          </p>
          <SpecEditor targetId={id} specs={specs} canEdit={canEdit} />
        </section>
      ) : (
        <section className="grid gap-3" aria-label="Flows">
          <p className="text-sm text-muted-foreground">
            The journeys that must never break ({MAX_FLOWS} at most). Every run on this app checks them first: the agent completes each one once and its
            steps are saved as a script; later runs replay the script without a model, and use the model only when the page changed.
          </p>
          <FlowEditor targetId={id} flows={flows} canEdit={canEdit} max={MAX_FLOWS} />
        </section>
      )}
    </main>
  );
}
