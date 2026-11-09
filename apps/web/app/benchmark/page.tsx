import { ChevronDown, Gauge } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";
import { EmptyState } from "@/components/empty-state";
import { TrendChart } from "@/components/trend-chart";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { decisions, latestPerProvider, perBug, percent, trend, type BenchmarkRow } from "@/lib/benchmark";
import { db } from "@/lib/db";
import { formatCost, formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "Benchmark" };

export default async function BenchmarkPage() {
  await connection();
  const rows: BenchmarkRow[] = await db.benchmarkResult.findMany({ orderBy: { createdAt: "desc" }, take: 200 });

  if (rows.length === 0) {
    return (
      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10">
        <Intro />
        <EmptyState icon={Gauge} title="No benchmark results yet">
          Run <code>npm run bench</code> (with <code>npm run dev</code> running) to measure recall,
          precision, false alarms and cost.
        </EmptyState>
      </main>
    );
  }

  const latest = latestPerProvider(rows);
  const newest = rows[0];
  const bugs = perBug(newest);
  const matches = decisions(newest);
  const quality = trend(rows, (r) => [r.recall, r.precision]);
  const cost = trend(rows, (r) => [r.avgCostUsd]);

  return (
    // minmax(0, 1fr): grid columns default to their widest content (the tables); this keeps
    // the page at screen width and lets wide tables scroll inside their own box instead.
    <main className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-10 px-4 py-10">
      <Intro />

      <section className="grid gap-4" aria-labelledby="latest-heading">
        <h2 id="latest-heading" className="text-lg font-semibold">
          Latest score per provider
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {latest.map((row) => (
            <div key={row.id} className="grid gap-4 rounded-xl border p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium">
                  {row.provider} <span className="text-muted-foreground">· {row.model}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(row.createdAt)} · <span className="font-mono">{row.gitCommit}</span>
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Tile label="Recall" value={percent(row.recall)} hint="planted bugs found" />
                <Tile label="Precision" value={percent(row.precision)} hint="reports that were real" />
                <Tile label="False alarms" value={row.falseAlarms.toFixed(1)} hint="per clean run" />
                <Tile label="Cost / run" value={formatCost(row.avgCostUsd)} hint={`${Math.round(row.avgDurationS)} s avg`} />
              </dl>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2" aria-label="Trends">
        <TrendChart
          title="Recall and precision across versions"
          points={quality}
          series={[
            { name: "Recall", color: "var(--series-1)" },
            { name: "Precision", color: "var(--series-2)" },
          ]}
          format="percent"
          max={1}
        />
        <TrendChart
          title="Average cost per run"
          points={cost}
          series={[{ name: "Cost", color: "var(--series-1)" }]}
          format="usd"
        />
      </section>

      <section className="grid gap-4" aria-labelledby="bugs-heading">
        <div>
          <h2 id="bugs-heading" className="text-lg font-semibold">
            Planted bugs, found or missed
          </h2>
          <p className="text-sm text-muted-foreground">
            Latest result ({newest.provider} · {newest.model}): how many of the {newest.runsBuggy} runs on the
            buggy shop found each bug.
          </p>
        </div>
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead>Planted bug</TableHead>
                <TableHead className="text-right">Found in</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bugs.map((bug) => (
                <TableRow key={bug.id}>
                  <TableCell className="tabular-nums text-muted-foreground">{bug.id}</TableCell>
                  <TableCell>{bug.title}</TableCell>
                  <TableCell className="text-right">
                    <span className="inline-flex items-center gap-2 tabular-nums">
                      <span className="flex gap-0.5" aria-hidden>
                        {Array.from({ length: newest.runsBuggy }, (_, i) => (
                          <span
                            key={i}
                            className={i < bug.foundRuns ? "size-2.5 rounded-sm bg-series-1" : "size-2.5 rounded-sm bg-muted"}
                          />
                        ))}
                      </span>
                      {bug.foundRuns} of {newest.runsBuggy}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="grid gap-4" aria-labelledby="all-heading">
        <h2 id="all-heading" className="text-lg font-semibold">
          All results
        </h2>
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Provider · model</TableHead>
                <TableHead>Commit</TableHead>
                <TableHead className="text-right">Recall</TableHead>
                <TableHead className="text-right">Precision</TableHead>
                <TableHead className="text-right">False alarms</TableHead>
                <TableHead className="text-right">Cost / run</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="whitespace-nowrap">{formatDate(row.createdAt)}</TableCell>
                  <TableCell>
                    {row.provider} · {row.model}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.gitCommit}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.recall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.precision)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.falseAlarms.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(row.avgCostUsd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="grid gap-2">
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-fit">
              <ChevronDown /> How reports were matched in the latest result ({matches.length})
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 grid gap-2 text-sm">
              {matches.map((m, i) => (
                <li key={i} className="rounded-lg border p-3">
                  <p className="font-medium">
                    {m.report} <span className="font-normal text-muted-foreground">({m.page})</span>
                  </p>
                  <p className="text-muted-foreground">
                    {m.matched ? `Matched planted bug #${m.matched}` : "No match (counts against precision)"}: {m.reason}
                  </p>
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      </section>
    </main>
  );
}

function Intro() {
  return (
    <div className="grid gap-2">
      <h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1>
      <p className="max-w-3xl text-muted-foreground">
        The agent runs against a demo shop with 12 planted bugs, and once against a clean copy with
        none. <b className="font-medium text-foreground">Recall</b> is the share of planted bugs it finds;{" "}
        <b className="font-medium text-foreground">precision</b> is the share of its reports that are real;
        every report on the clean copy is a <b className="font-medium text-foreground">false alarm</b>.
        Reports are matched to planted bugs by page and a model judgement, and every match is listed
        below for spot checks.
      </p>
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      <dd className="text-xs text-muted-foreground">{hint}</dd>
    </div>
  );
}
