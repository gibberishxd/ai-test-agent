"use client";

import { Check, Copy, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { SeverityBadge } from "@/components/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { evidenceLines, toGitHubIssue, toJira } from "@/lib/export";
import { fileUrl } from "@/lib/file-url";
import type { BugView } from "@/lib/serialize";

type Props = { bug: BugView; runUrl: string; targetUrl: string; filesToken?: string | null };

export function BugCard({ bug, runUrl, targetUrl, filesToken = null }: Props) {
  const evidence = evidenceLines(bug.evidence);
  const replay = typeof bug.evidence.replay === "string" ? bug.evidence.replay : null;
  const context = { runUrl, targetUrl };

  return (
    <Card data-testid="bug-card">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={bug.severity} />
          <Badge variant="outline">{bug.category}</Badge>
          {bug.source === "deterministic" ? (
            <Badge variant="secondary">Automatic check</Badge>
          ) : bug.status === "confirmed" ? (
            <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
              <ShieldCheck /> Confirmed by replay
            </Badge>
          ) : (
            <Badge variant="secondary">Not verified yet</Badge>
          )}
        </div>
        <CardTitle className="text-base leading-snug">{bug.title}</CardTitle>
        <a href={bug.pageUrl} target="_blank" rel="noreferrer" className="w-fit truncate text-sm text-muted-foreground hover:underline">
          {bug.pageUrl}
        </a>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {bug.reproSteps.length > 0 && (
          <section>
            <h4 className="mb-1 font-medium">Steps to reproduce</h4>
            <ol className="list-decimal space-y-0.5 pl-5">
              {bug.reproSteps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </section>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <section className="rounded-lg bg-muted/50 p-3">
            <h4 className="mb-1 font-medium">Expected</h4>
            <p className="text-muted-foreground">{bug.expected || "—"}</p>
          </section>
          <section className="rounded-lg bg-muted/50 p-3">
            <h4 className="mb-1 font-medium">Actual</h4>
            <p className="text-muted-foreground">{bug.actual || "—"}</p>
          </section>
        </div>
        {evidence.length > 0 && (
          <section>
            <h4 className="mb-1 font-medium">Evidence</h4>
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">
              {evidence.join("\n")}
            </pre>
          </section>
        )}
        {(bug.reasoning || replay) && (
          <section className="grid gap-1 text-muted-foreground">
            {bug.reasoning && (
              <p>
                <span className="font-medium text-foreground">Agent&apos;s reasoning: </span>
                {bug.reasoning}
              </p>
            )}
            {replay && (
              <p>
                <span className="font-medium text-foreground">Replay: </span>
                {replay}
              </p>
            )}
          </section>
        )}
        {bug.screenshot && (
          // eslint-disable-next-line @next/next/no-img-element -- served by our own API route
          <img
            src={fileUrl(bug.screenshot, filesToken)}
            alt={`Screenshot of ${bug.pageUrl}`}
            className="max-h-80 w-full rounded-lg border object-cover object-top"
            loading="lazy"
          />
        )}
        <div className="flex flex-wrap gap-2">
          <CopyButton label="Copy as GitHub issue" text={() => toGitHubIssue(bug, context)} />
          <CopyButton label="Copy for Jira" text={() => toJira(bug, context)} />
        </div>
      </CardContent>
    </Card>
  );
}

function CopyButton({ label, text }: { label: string; text: () => string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text());
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy. Your browser blocked clipboard access.");
    }
  };
  return (
    <Button variant="outline" size="sm" onClick={copy}>
      {copied ? <Check /> : <Copy />}
      {label}
    </Button>
  );
}
