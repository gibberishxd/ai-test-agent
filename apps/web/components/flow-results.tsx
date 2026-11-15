import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import { flowStatus } from "@/lib/flow-status";
import { formatEstimate } from "@/lib/format";
import type { FlowResultView } from "@/lib/serialize";

/** The run report's critical flows (run 7, M4): one line per journey, how it went and what it cost. */
export function FlowResults({ flows }: { flows: FlowResultView[] }) {
  if (flows.length === 0) return null;
  return (
    <section className="grid gap-3" aria-labelledby="flows-heading" data-testid="flow-results">
      <h2 id="flows-heading" className="text-lg font-semibold">
        Critical flows
      </h2>
      <ul className="grid gap-2">
        {flows.map((flow, i) => {
          const status = flowStatus(flow.status);
          const Icon = status.good === true ? CheckCircle2 : status.good === false ? XCircle : CircleDashed;
          return (
            <li key={i} className="grid gap-1 rounded-xl border p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2 font-medium">
                  <Icon className={`size-4 shrink-0 ${status.good === true ? "text-emerald-600" : status.good === false ? "text-destructive" : "text-muted-foreground"}`} />
                  <span className="truncate">{flow.name}</span>
                </span>
                <span className="text-muted-foreground">
                  {status.label}
                  {!flow.replayed && flow.modelCalls > 0 && (
                    <>
                      {" "}
                      · {flow.modelCalls} model call{flow.modelCalls === 1 ? "" : "s"} · {formatEstimate(flow.estimatedCostUsd)}
                    </>
                  )}
                </span>
              </div>
              {flow.detail && <p className="text-muted-foreground">{flow.detail}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
