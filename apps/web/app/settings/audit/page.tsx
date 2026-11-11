import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { db } from "@/lib/db";
import { formatDate } from "@/lib/format";
import { can } from "@/lib/roles";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Audit log" };
const LIMIT = 200;

/** Who did what, when: API keys, models, sign-in setups, webhooks, triage, members, runs. */
export default async function AuditPage() {
  const context = await currentContext();
  if (!context.signedIn) redirect("/signin");
  if (!can(context.role ?? null, "audit.view")) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-muted-foreground">Only owners and admins can read the audit log.</p>
      </main>
    );
  }
  const rows = await db.auditLog.findMany({
    where: { workspaceId: context.workspaceId },
    orderBy: { createdAt: "desc" },
    take: LIMIT,
    include: { user: { select: { email: true } } },
  });
  return (
    <main className="mx-auto grid max-w-5xl gap-6 px-4 py-10">
      <Link href="/settings" className="text-sm text-muted-foreground hover:underline">
        ← Settings
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>The latest {LIMIT} changes in this workspace. Secrets are never recorded.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table data-testid="audit-table">
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Who</TableHead>
                <TableHead>What</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="whitespace-nowrap">{formatDate(row.createdAt)}</TableCell>
                  <TableCell>{row.user?.email ?? (row.metadata && (row.metadata as Record<string, unknown>).apiKeyId ? "API key" : "system")}</TableCell>
                  <TableCell className="font-mono text-xs">{row.action}</TableCell>
                  <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                    {[row.targetUrl, JSON.stringify(row.metadata ?? {})].filter((v) => v && v !== "{}").join(" · ")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
