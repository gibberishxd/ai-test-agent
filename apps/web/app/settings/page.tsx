import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { DomainList } from "@/components/domain-list";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { currentUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { formatCost, formatDate, hostOf } from "@/lib/format";
import { auditLog, listDomains, usageThisMonth } from "@/lib/settings-data";

export const metadata: Metadata = { title: "Settings" };

const ACTIONS: Record<string, string> = {
  "run.started": "Started a run",
  "domain.verified": "Verified a domain",
  "share.created": "Shared a report",
  "share.revoked": "Revoked a share link",
};

export default async function SettingsPage() {
  const user = await currentUser();
  if (!user) redirect("/signin");

  const [workspace, domains, usage, log] = await Promise.all([
    db.workspace.findUniqueOrThrow({ where: { id: user.workspaceId } }),
    listDomains(user.workspaceId),
    usageThisMonth(user.workspaceId),
    auditLog(user.workspaceId),
  ]);
  const used = Math.min(usage.runs / usage.quota, 1);

  return (
    <main className="mx-auto grid max-w-4xl gap-8 px-4 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-muted-foreground">Signed in as {user.email}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Usage this month</CardTitle>
          <CardDescription>
            {usage.runs} of {usage.quota} runs · {formatCost(usage.costUsd)} spent on AI models
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div
            className="h-2 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={usage.quota}
            aria-valuenow={usage.runs}
            aria-label="Runs used this month"
          >
            <div className="h-full rounded-full bg-primary" style={{ width: `${used * 100}%` }} />
          </div>
          {usage.byProvider.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead className="text-right">Runs</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usage.byProvider.map((row) => (
                  <TableRow key={row.provider}>
                    <TableCell>{row.provider}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.runs}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCost(row.costUsd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Domains for interactive tests</CardTitle>
          <CardDescription>
            Interactive tests type into forms and click buttons, so they only run on domains you
            prove you own. Passive scans work on any public URL.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DomainList
            token={workspace.verificationToken}
            domains={domains.map((d) => ({
              id: d.id,
              hostname: d.hostname,
              verifiedAt: d.verifiedAt?.toISOString() ?? null,
              method: d.method,
            }))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>Who did what in this workspace, newest first.</CardDescription>
        </CardHeader>
        <CardContent>
          {log.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Who</TableHead>
                    <TableHead>What</TableHead>
                    <TableHead>Target</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {log.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-muted-foreground">{formatDate(entry.createdAt)}</TableCell>
                      <TableCell>{entry.user?.email ?? "visitor"}</TableCell>
                      <TableCell>
                        {ACTIONS[entry.action] ?? entry.action}
                        {entry.mode ? ` (${entry.mode})` : ""}
                      </TableCell>
                      <TableCell className="max-w-48 truncate">
                        {entry.runId ? (
                          <Link href={`/runs/${entry.runId}`} className="hover:underline">
                            {entry.targetUrl ? hostOf(entry.targetUrl) : "run"}
                          </Link>
                        ) : entry.targetUrl ? (
                          hostOf(entry.targetUrl)
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
