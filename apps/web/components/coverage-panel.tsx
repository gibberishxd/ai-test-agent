"use client";

import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Coverage } from "@/lib/serialize";

const PHASES: Record<string, string> = {
  map: "Mapping the app",
  plan: "Writing the test plan",
  execute: "Working through the plan",
  review: "Reviewing candidates",
  done: "Finished",
};

/** Ticked, skipped or open: one line per plan item. */
export function itemStatus(coverage: Coverage, id: string): string {
  return coverage.progress?.[id]?.status ?? "open";
}

export function coverageCounts(coverage: Coverage) {
  const plan = coverage.plan ?? [];
  const ticked = plan.filter((item) => itemStatus(coverage, item.id) !== "open").length;
  return { items: plan.length, ticked, pages: coverage.map?.pages?.length ?? 0 };
}

/** What a deep run covered: its map of the app, its test plan and how far it got (run 9). */
export function CoveragePanel({ coverage }: { coverage: Coverage }) {
  const { items, ticked, pages } = coverageCounts(coverage);
  const plan = coverage.plan ?? [];
  const viewports = Object.keys(coverage.screenshots ?? {});
  return (
    <Card>
      <CardHeader>
        <CardTitle>Coverage</CardTitle>
        <CardDescription data-testid="coverage-summary">
          {PHASES[coverage.phase ?? ""] ?? "Starting"} · {pages} page{pages === 1 ? "" : "s"} mapped · {ticked} of {items} plan
          item{items === 1 ? "" : "s"} done
          {viewports.length > 0 && <> · screenshots at {viewports.join(", ")}</>}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {coverage.map?.summary && <p className="text-sm text-muted-foreground">{coverage.map.summary}</p>}
        {plan.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-fit">
                <ChevronDown /> Test plan ({ticked}/{items})
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-2 grid gap-1 text-sm">
                {plan.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-baseline gap-2">
                    <Badge variant="outline" className="capitalize">
                      {itemStatus(coverage, item.id)}
                    </Badge>
                    <span className="text-muted-foreground">
                      {item.area}
                      {item.viewport ? ` · ${item.viewport}` : ""}
                    </span>
                    <span>{item.description}</span>
                  </li>
                ))}
              </ul>
              {(coverage.not_applicable ?? []).length > 0 && (
                <ul className="mt-3 grid gap-1 text-sm text-muted-foreground">
                  {(coverage.not_applicable ?? []).map((n) => (
                    <li key={n.area}>
                      Not applicable: {n.area} ({n.reason})
                    </li>
                  ))}
                </ul>
              )}
            </CollapsibleContent>
          </Collapsible>
        )}
        {(coverage.map?.pages ?? []).length > 0 && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-fit">
                <ChevronDown /> Map of the app ({pages} pages)
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-2 grid gap-1 text-sm">
                {(coverage.map?.pages ?? []).map((page) => (
                  <li key={page.url}>
                    <span className="font-medium break-all">{page.url}</span>
                    {page.purpose && <span className="text-muted-foreground"> · {page.purpose}</span>}
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}
