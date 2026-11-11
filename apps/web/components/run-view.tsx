"use client";

import { ChevronDown, Download, Link2Off, Loader2, OctagonX, SearchCheck, Share2, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ModeBadge, StatusBadge } from "@/components/badges";
import { BugCard } from "@/components/bug-card";
import { EmptyState } from "@/components/empty-state";
import { LivePane } from "@/components/live-pane";
import { StepTimeline } from "@/components/step-timeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { SEVERITIES } from "@/lib/contracts/types";
import { formatCost, formatDuration, isFinal } from "@/lib/format";
import type { BugView, RunView as Run } from "@/lib/serialize";

const POLL_MS = 1500;

const bySeverity = (a: BugView, b: BugView) =>
  SEVERITIES.indexOf(a.severity as never) - SEVERITIES.indexOf(b.severity as never);

type Props = {
  initial: Run;
  /** Shared, read-only view: no Stop, no sharing controls, no polling. */
  readOnly?: boolean;
  /** Signed-in members of the run's workspace can create and revoke share links. */
  canShare?: boolean;
  /** Members can mark findings confirmed, false positive or won't fix. */
  canTriage?: boolean;
  shareToken?: string | null;
  /** On a shared report: the token that lets this viewer load the run's screenshots. */
  filesToken?: string | null;
};

export function RunView({
  initial,
  readOnly = false,
  canShare = false,
  canTriage = false,
  shareToken = null,
  filesToken = null,
}: Props) {
  const [run, setRun] = useState(initial);
  const [now, setNow] = useState(() => Date.now());
  const [stopping, setStopping] = useState(false);
  const final = isFinal(run.status);

  // Poll while the run is in progress; stop as soon as it reaches a final status.
  useEffect(() => {
    if (final || readOnly) return;
    const timer = setInterval(async () => {
      setNow(Date.now());
      const response = await fetch(`/api/runs/${run.id}`, { cache: "no-store" }).catch(() => null);
      if (response?.ok) setRun(await response.json());
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [final, readOnly, run.id]);

  const stop = async () => {
    setStopping(true);
    const response = await fetch(`/api/runs/${run.id}/stop`, { method: "POST" });
    if (!response.ok) toast.error("This run has already finished.");
  };

  const runUrl = typeof window === "undefined" ? `/runs/${run.id}` : window.location.href;
  const shown = run.bugs.filter((bug) => bug.status !== "dismissed" && !bug.suppressed).sort(bySeverity);
  const history = run.history ?? null;
  const dismissed = run.bugs.filter((bug) => bug.status === "dismissed");
  const counts = Object.fromEntries(SEVERITIES.map((s) => [s, shown.filter((b) => b.severity === s).length]));

  return (
    <div className="grid gap-8">
      <header className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={run.status} />
          <ModeBadge mode={run.mode} />
          {run.stopRequested && !final && <span className="text-sm text-muted-foreground">Stopping…</span>}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight break-all">{run.targetUrl}</h1>
        {run.focus && <p className="text-muted-foreground">Focus: {run.focus}</p>}
        <div className="flex flex-wrap gap-2">
          {!final && !readOnly && (
            <Button variant="outline" onClick={stop} disabled={stopping || run.stopRequested}>
              <Square /> Stop
            </Button>
          )}
          {final && (
            <Button variant="outline" asChild>
              <a href={`/api/runs/${run.id}/report`} download>
                <Download /> Download JSON
              </a>
            </Button>
          )}
          {final && canShare && !readOnly && <ShareControl runId={run.id} initialToken={shareToken} />}
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Run summary">
        <Stat label="Pages visited" value={String(run.pagesVisited)} />
        <Stat label="Steps" value={String(run.stepCount)} />
        <Stat label="Duration" value={formatDuration(run.startedAt, run.finishedAt, now)} />
        <Stat label="Cost" value={formatCost(run.costUsd)} hint={run.model ? `${run.provider} · ${run.model}` : undefined} />
      </section>

      {run.status === "queued" && (
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Waiting for a worker to pick up this run…
          </CardContent>
        </Card>
      )}

      {run.status === "failed" && (
        <Card className="border-destructive/50">
          <CardContent className="flex gap-3 text-sm">
            <OctagonX className="size-5 shrink-0 text-destructive" />
            <div>
              <p className="font-medium">The run failed</p>
              <p className="text-muted-foreground">{run.error ?? "Unknown error."}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <LivePane steps={run.steps} live={!final && !readOnly} filesToken={filesToken} />

      <section className="grid gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">
            {final ? "Bugs found" : "Bugs found so far"} <span className="text-muted-foreground">({shown.length})</span>
          </h2>
          <p className="text-sm text-muted-foreground">
            {SEVERITIES.map((s) => `${counts[s]} ${s}`).join(" · ")}
          </p>
        </div>
        {shown.length === 0 ? (
          <EmptyState icon={SearchCheck} title={final ? "No bugs found" : "Nothing yet"}>
            {final
              ? "Every check passed and nothing the agent reported survived replay."
              : "Bugs appear here as soon as they're found."}
          </EmptyState>
        ) : (
          <div className="grid gap-4">
            {shown.map((bug) => (
              <BugCard
                key={bug.id}
                bug={bug}
                runUrl={runUrl}
                targetUrl={run.targetUrl}
                filesToken={filesToken}
                change={history?.previousRunId ? history.change[bug.id] : undefined}
                triage={bug.fingerprint ? history?.triage[bug.fingerprint] : undefined}
                canTriage={canTriage && !readOnly && Boolean(bug.fingerprint)}
              />
            ))}
          </div>
        )}
        {history && history.fixed.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-fit" data-testid="fixed-since">
                <ChevronDown /> Fixed since the previous run ({history.fixed.length})
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-2 grid gap-2 text-sm">
                {history.fixed.map((bug, i) => (
                  <li key={i} className="rounded-lg border p-3">
                    <p className="font-medium">{bug.title}</p>
                    <p className="text-muted-foreground">
                      {bug.severity} · {bug.pageUrl}
                    </p>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
        {history && history.suppressed > 0 && (
          <p className="text-sm text-muted-foreground">
            {history.suppressed} finding{history.suppressed === 1 ? " was" : "s were"} hidden: your team marked{" "}
            {history.suppressed === 1 ? "it" : "them"} as a false positive in an earlier run.
          </p>
        )}
        {dismissed.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-fit">
                <ChevronDown /> Dismissed by replay or as duplicates ({dismissed.length})
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-2 grid gap-2 text-sm">
                {dismissed.map((bug) => (
                  <li key={bug.id} className="rounded-lg border p-3">
                    <p className="font-medium">{bug.title}</p>
                    <p className="text-muted-foreground">{bug.dismissReason}</p>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
      </section>

      <section className="grid gap-4">
        <h2 className="text-lg font-semibold">Timeline</h2>
        {run.steps.length === 0 ? (
          <p className="text-sm text-muted-foreground">No steps yet.</p>
        ) : final ? (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-fit">
                <ChevronDown /> Show all {run.steps.length} steps
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <StepTimeline steps={run.steps} filesToken={filesToken} />
            </CollapsibleContent>
          </Collapsible>
        ) : (
          <StepTimeline steps={[...run.steps].reverse()} filesToken={filesToken} />
        )}
      </section>
    </div>
  );
}

function ShareControl({ runId, initialToken }: { runId: string; initialToken: string | null }) {
  const [url, setUrl] = useState<string | null>(
    initialToken && typeof window !== "undefined" ? `${window.location.origin}/share/${initialToken}` : null,
  );
  const [busy, setBusy] = useState(false);

  const share = async () => {
    setBusy(true);
    const response = await fetch(`/api/runs/${runId}/share`, { method: "POST" });
    const data = await response.json();
    setBusy(false);
    if (!response.ok) return toast.error(data.error ?? "Couldn't create a link.");
    setUrl(data.url);
    await navigator.clipboard?.writeText(data.url).catch(() => undefined);
    toast.success("Share link copied. Anyone with the link can view this report.");
  };

  const revoke = async () => {
    setBusy(true);
    const response = await fetch(`/api/runs/${runId}/share`, { method: "DELETE" });
    setBusy(false);
    if (!response.ok) return toast.error("Couldn't revoke the link.");
    setUrl(null);
    toast.success("Link revoked. The old URL no longer works.");
  };

  return url ? (
    <span className="flex flex-wrap items-center gap-2">
      <input
        readOnly
        value={url}
        aria-label="Share link"
        className="h-8 w-64 max-w-full rounded-md border bg-muted px-2 text-xs"
        onFocus={(event) => event.currentTarget.select()}
      />
      <Button variant="ghost" size="sm" onClick={revoke} disabled={busy}>
        <Link2Off /> Revoke
      </Button>
    </span>
  ) : (
    <Button variant="outline" onClick={share} disabled={busy}>
      <Share2 /> Share read-only link
    </Button>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
