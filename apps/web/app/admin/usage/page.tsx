import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCost } from "@/lib/format";
import { platformUsage } from "@/lib/usage";
import { currentContext } from "@/lib/workspace";

export const metadata: Metadata = { title: "Usage across workspaces" };

/**
 * For the service's operators (users.is_platform_admin, set with `worker make-admin`): usage
 * across every workspace this month. The database checks the flag; anyone else gets a 404.
 */
export default async function AdminUsagePage() {
  const context = await currentContext();
  if (!context.signedIn || !context.userId) redirect("/signin");
  const rows = await platformUsage(context.userId);
  if (!rows) notFound();
  const total = rows.reduce((sum, r) => sum + r.explorerCostUsd + r.reviewerCostUsd, 0);

  return (
    <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle>Usage across workspaces</CardTitle>
          <CardDescription>
            This month: {rows.reduce((sum, r) => sum + r.runs, 0)} runs, {formatCost(total)} model cost, {rows.length} workspaces.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table data-testid="admin-usage-table">
            <TableHeader>
              <TableRow>
                <TableHead>Workspace</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead className="text-right">Members</TableHead>
                <TableHead className="text-right">Runs</TableHead>
                <TableHead className="text-right">Explorer cost</TableHead>
                <TableHead className="text-right">Reviewer cost</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.workspaceId}>
                  <TableCell>
                    {row.name} <span className="text-xs text-muted-foreground">{row.slug}</span>
                  </TableCell>
                  <TableCell>{row.planId}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.members}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.runs}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(row.explorerCostUsd)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(row.reviewerCostUsd)}</TableCell>
                  <TableCell className="text-right tabular-nums">{(row.inputTokens + row.outputTokens).toLocaleString("en")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
