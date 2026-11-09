import { History } from "lucide-react";
import Link from "next/link";
import { ModeBadge, StatusBadge } from "@/components/badges";
import { EmptyState } from "@/components/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCost, formatDate, hostOf } from "@/lib/format";
import type { RunRow } from "@/lib/runs";

type Summary = { by_severity?: Record<string, number> };

function SeverityCounts({ summary }: { summary: Summary | null }) {
  const counts = summary?.by_severity;
  if (!counts) return <span className="text-muted-foreground">—</span>;
  const items = [
    ["critical", "bg-red-600"],
    ["high", "bg-orange-500"],
    ["medium", "bg-amber-400"],
    ["low", "bg-muted-foreground/40"],
  ] as const;
  return (
    <span className="flex items-center gap-2 tabular-nums">
      {items.map(([severity, color]) => (
        <span key={severity} className="flex items-center gap-1" title={`${severity}: ${counts[severity] ?? 0}`}>
          <span className={`size-2 rounded-full ${color}`} aria-hidden />
          <span className="sr-only">{severity}</span>
          {counts[severity] ?? 0}
        </span>
      ))}
    </span>
  );
}

export function RunHistory({ runs }: { runs: RunRow[] }) {
  if (runs.length === 0) {
    return (
      <EmptyState icon={History} title="No runs yet">
        Start a test above. Every run shows up here with its status, bugs and cost.
      </EmptyState>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Target</TableHead>
            <TableHead>Mode</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Bugs by severity</TableHead>
            <TableHead className="text-right">Cost</TableHead>
            <TableHead className="text-right">Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id}>
              <TableCell className="max-w-56 truncate font-medium">
                <Link href={`/runs/${run.id}`} className="hover:underline">
                  {hostOf(run.targetUrl)}
                </Link>
              </TableCell>
              <TableCell>
                <ModeBadge mode={run.mode} />
              </TableCell>
              <TableCell>
                <StatusBadge status={run.status} />
              </TableCell>
              <TableCell>
                <SeverityCounts summary={run.summary as Summary | null} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{formatCost(run.costUsd)}</TableCell>
              <TableCell className="text-right whitespace-nowrap text-muted-foreground">
                {formatDate(run.createdAt)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
