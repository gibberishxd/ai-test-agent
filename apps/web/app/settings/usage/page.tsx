import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCost, formatDate } from "@/lib/format";
import { workspaceUsage } from "@/lib/usage";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Usage" };

/** This month's runs and model cost against the workspace's plan (run 5, K4). */
export default async function UsagePage() {
  const context = await currentContext();
  if (!context.signedIn) redirect("/signin");
  const usage = await workspaceUsage(context.workspaceId);
  const { plan } = usage;
  const limits = [
    { label: "Runs this month", value: `${usage.runs} of ${usage.quota}`, share: usage.runs / usage.quota },
    { label: "Members", value: `${usage.seatsUsed} of ${plan.seats} seats`, share: usage.seatsUsed / plan.seats },
    { label: "Steps per run", value: `up to ${plan.maxStepsPerRun}`, share: null },
    { label: "Models", value: plan.allowedProviders.length ? plan.allowedProviders.join(", ") : "any provider", share: null },
    { label: "Kept for", value: `${usage.retentionDays} days`, share: null },
  ];

  return (
    <main className="mx-auto grid max-w-5xl gap-6 px-4 py-10">
      <Link href="/settings" className="text-sm text-muted-foreground hover:underline">
        ← Settings
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>
            {plan.name} plan <span className="text-sm font-normal text-muted-foreground">since {formatDate(usage.since)}</span>
          </CardTitle>
          <CardDescription>
            Limits are enforced by the database when a run starts. Model cost this month: <strong>{formatCost(usage.costUsd)}</strong>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="plan-limits">
            {limits.map((limit) => (
              <div key={limit.label} className="grid gap-1 rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">{limit.label}</dt>
                <dd className="font-medium tabular-nums">{limit.value}</dd>
                {limit.share !== null && (
                  <div className="h-1.5 rounded-full bg-muted" aria-hidden>
                    <div
                      className={`h-1.5 rounded-full ${limit.share >= 1 ? "bg-destructive" : "bg-primary"}`}
                      style={{ width: `${Math.min(100, Math.round(limit.share * 100))}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Per model</CardTitle>
          <CardDescription>The explorer drives the browser; the reviewer judges flagged steps and reports. Their costs are recorded apart.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {usage.byModel.length === 0 ? (
            <p className="text-sm text-muted-foreground">No finished runs this month yet.</p>
          ) : (
            <Table data-testid="usage-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Role</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Runs</TableHead>
                  <TableHead className="text-right">Tokens in / out</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usage.byModel.map((row) => (
                  <TableRow key={`${row.role}-${row.provider}-${row.model}`}>
                    <TableCell className="capitalize">{row.role}</TableCell>
                    <TableCell>
                      {row.provider} · {row.model}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.runs}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.inputTokens.toLocaleString("en")} / {row.outputTokens.toLocaleString("en")}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatCost(row.costUsd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
