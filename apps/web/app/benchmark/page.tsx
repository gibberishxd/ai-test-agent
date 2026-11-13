import { ChevronDown, Gauge } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";
import { EmptyState } from "@/components/empty-state";
import { TrendChart } from "@/components/trend-chart";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  commitLabel,
  decisions,
  holdout,
  holdoutPerBug,
  judgeLabel,
  latestPerProvider,
  validResults,
  leaderboardFromView,
  reviewerLabel,
  perBug,
  percent,
  percentOrDash,
  trend,
  verification,
  type BenchmarkRow,
  type PerBug,
  type Verification,
} from "@/lib/benchmark";
import { db } from "@/lib/db";
import { formatCost, formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "Benchmark" };

export default async function BenchmarkPage() {
  await connection();
  const rows: BenchmarkRow[] = validResults(await db.benchmarkResult.findMany({ orderBy: { createdAt: "desc" }, take: 200 }));

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
  const fromView = await db.$queryRaw<{ id: string }[]>`SELECT latest_result_id AS id FROM model_leaderboard`;
  const board = leaderboardFromView(rows, fromView.map((r) => r.id));
  const newest = rows[0];
  const bugs = perBug(newest);
  const holdoutBugs = holdoutPerBug(newest);
  const newestHoldout = holdout(newest);
  const matches = decisions(newest);
  const quality = trend(rows, (r) => [r.recall, r.precision]);
  const cost = trend(rows, (r) => [r.avgCostUsd]);

  return (
    // minmax(0, 1fr): grid columns default to their widest content (the tables); this keeps
    // the page at screen width and lets wide tables scroll inside their own box instead.
    <main className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-10 px-4 py-10">
      <Intro />

      <section className="grid gap-4" aria-labelledby="leaderboard-heading">
        <div>
          <h2 id="leaderboard-heading" className="text-lg font-semibold">
            Model leaderboard
          </h2>
          <p className="text-sm text-muted-foreground">
            Bring any model, and see how it performs here before you trust it. One row per model (its newest
            result), ranked by AI-only recall.
          </p>
        </div>
        <div className="overflow-x-auto rounded-xl border">
          <Table data-testid="leaderboard">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">#</TableHead>
                <TableHead>Provider · model</TableHead>
                <TableHead className="text-right">AI-only recall</TableHead>
                <TableHead className="text-right">Recall</TableHead>
                <TableHead className="text-right">Precision</TableHead>
                <TableHead className="text-right">False alarms</TableHead>
                <TableHead className="text-right">Holdout AI-only</TableHead>
                <TableHead className="text-right">Reported → verified</TableHead>
                <TableHead className="text-right">Correct but discarded</TableHead>
                <TableHead className="text-right">Cost / run</TableHead>
                <TableHead className="text-right">Time / run</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {board.map((row, i) => (
                <TableRow key={row.id}>
                  <TableCell className="tabular-nums text-muted-foreground">{i + 1}</TableCell>
                  <TableCell>
                    {row.provider} <span className="text-muted-foreground">· {row.model}</span>
                    {reviewerLabel(row) && <span className="block text-xs text-muted-foreground">+ reviewer {reviewerLabel(row)}</span>}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{percentOrDash(row.aiRecall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.recall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.precision)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.falseAlarms.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percentOrDash(holdout(row)?.aiRecall)}</TableCell>
                  <TableCell className="text-right tabular-nums whitespace-nowrap">
                    {funnelLabel(verification(row))}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{verification(row)?.correctButDiscarded ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(row.avgCostUsd)}</TableCell>
                  <TableCell className="text-right tabular-nums">{Math.round(row.avgDurationS)} s</TableCell>
                  <TableCell className="whitespace-nowrap">{formatDate(row.createdAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

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
                  {formatDate(row.createdAt)} · <span className="font-mono">{commitLabel(row)}</span>
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Tile
                  label="AI-only recall"
                  value={percentOrDash(row.aiRecall)}
                  hint="bugs that need judgement"
                  headline
                />
                <Tile label="Recall" value={percent(row.recall)} hint="all planted bugs" />
                <Tile label="Precision" value={percent(row.precision)} hint="reports that were real" />
                <Tile label="False alarms" value={row.falseAlarms.toFixed(1)} hint="per clean run" />
                <Tile label="Holdout AI-only" value={percentOrDash(holdout(row)?.aiRecall)} hint="app never tuned for" />
                <Tile label="Cost / run" value={formatCost(row.avgCostUsd)} hint={`${Math.round(row.avgDurationS)} s avg`} />
              </dl>
              <VerificationSummary funnel={verification(row)} />
              <p className="text-xs text-muted-foreground">
                Judge: {judgeLabel(row)}
                {reviewerLabel(row) && <> · Reviewer: {reviewerLabel(row)}</>}
              </p>
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
            buggy shop found each bug. &ldquo;AI&rdquo; bugs need judgement; &ldquo;checks&rdquo; bugs are
            found by the free deterministic checks whatever the model.
          </p>
        </div>
        <BugTable bugs={bugs} runs={newest.runsBuggy} />
      </section>

      {newestHoldout && holdoutBugs.length > 0 && (
        <section className="grid gap-4" aria-labelledby="holdout-heading">
          <div>
            <h2 id="holdout-heading" className="text-lg font-semibold">
              Holdout app: found or missed
            </h2>
            <p className="text-sm text-muted-foreground">
              A separate booking app with the same kinds of bugs and different specifics. Prompts are never
              tuned against it, so a score here that is close to the shop&rsquo;s shows the agent isn&rsquo;t
              overfitted to the shop. AI-only recall {percentOrDash(newestHoldout.aiRecall)}, recall{" "}
              {percent(newestHoldout.recall)}, false alarms {newestHoldout.falseAlarms?.toFixed(1) ?? "—"} per
              clean run.
            </p>
          </div>
          <BugTable bugs={holdoutBugs} runs={newestHoldout.runsBuggy} />
        </section>
      )}

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
                <TableHead className="text-right">AI-only</TableHead>
                <TableHead className="text-right">Recall</TableHead>
                <TableHead className="text-right">Holdout AI-only</TableHead>
                <TableHead className="text-right">Precision</TableHead>
                <TableHead className="text-right">False alarms</TableHead>
                <TableHead className="text-right">Cost / run</TableHead>
                <TableHead>Judge</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="whitespace-nowrap">{formatDate(row.createdAt)}</TableCell>
                  <TableCell>
                    {row.provider} · {row.model}
                    {reviewerLabel(row) && <span className="block text-xs text-muted-foreground">+ reviewer {reviewerLabel(row)}</span>}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{commitLabel(row)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percentOrDash(row.aiRecall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.recall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percentOrDash(holdout(row)?.aiRecall)}</TableCell>
                  <TableCell className="text-right tabular-nums">{percent(row.precision)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.falseAlarms.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(row.avgCostUsd)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{judgeLabel(row)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="grid gap-2">
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="h-auto w-fit max-w-full py-1.5 text-left whitespace-normal">
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
        The agent runs against a demo shop with 13 planted bugs (one behind a login), and once against a clean copy with
        none. <b className="font-medium text-foreground">AI-only recall</b> counts only the bugs that need
        judgement (the free deterministic checks find the others whatever the model), so it is the number
        to compare models by. <b className="font-medium text-foreground">Recall</b> is the share of all planted bugs found;{" "}
        <b className="font-medium text-foreground">precision</b> is the share of its reports that are real;
        every report on the clean copy is a <b className="font-medium text-foreground">false alarm</b>.
        Reports are matched to planted bugs by page and a model judgement (the judge is shown with each
        result), and every match is listed below for spot checks. A separate holdout app, never used to
        tune prompts, checks that the agent isn&rsquo;t overfitted to the shop.
      </p>
    </div>
  );
}

function BugTable({ bugs, runs }: { bugs: PerBug[]; runs: number }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>Planted bug</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead className="text-right">Found in</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {bugs.map((bug) => (
            <TableRow key={bug.id}>
              <TableCell className="tabular-nums text-muted-foreground">{bug.id}</TableCell>
              <TableCell>{bug.title}</TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {bug.needsJudgement === null ? "—" : bug.needsJudgement ? "AI" : "checks"}
              </TableCell>
              <TableCell className="text-right">
                <span className="inline-flex items-center gap-2 tabular-nums">
                  <span className="flex gap-0.5" aria-hidden>
                    {Array.from({ length: runs }, (_, i) => (
                      <span
                        key={i}
                        className={i < bug.foundRuns ? "size-2.5 rounded-sm bg-series-1" : "size-2.5 rounded-sm bg-muted"}
                      />
                    ))}
                  </span>
                  {bug.foundRuns} of {runs}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Tile({ label, value, hint, headline = false }: { label: string; value: string; hint: string; headline?: boolean }) {
  return (
    <div>
      <dt className={headline ? "text-sm font-medium" : "text-sm text-muted-foreground"}>{label}</dt>
      <dd className={headline ? "mt-1 text-3xl font-semibold tabular-nums" : "mt-1 text-2xl font-semibold tabular-nums"}>{value}</dd>
      <dd className="text-xs text-muted-foreground">{hint}</dd>
    </div>
  );
}

function funnelLabel(funnel: Verification | null): string {
  return funnel ? `${funnel.reported} → ${funnel.verified}` : "—";
}

/** What replay verification threw away, so a too-strict verifier is visible (run 3). */
function VerificationSummary({ funnel }: { funnel: Verification | null }) {
  if (!funnel) return null;
  return (
    <div className="grid gap-1 rounded-lg bg-muted/50 p-3 text-sm" data-testid="verification-summary">
      <p>
        <span className="font-medium">Verification:</span> {funnel.reported} reported → {funnel.verified} verified (
        {funnel.duplicates} duplicates, {funnel.discardedAtReplay} discarded at replay).
      </p>
      <p>
        <span className="font-medium">Correct but discarded: {funnel.correctButDiscarded}</span>
        {funnel.bugsLost > 0 && <> ({funnel.bugsLost} planted bug(s) lost)</>}. Before verification: AI-only recall{" "}
        {percent(funnel.aiRecallBefore)}, false alarms {funnel.falseAlarmsBefore.toFixed(1)} per clean run.
      </p>
      {funnel.reasons.length > 0 && (
        <p className="text-muted-foreground">
          Discarded because: {funnel.reasons.map(([reason, n]) => `${reason.replaceAll("_", " ")} ${n}`).join(", ")}
        </p>
      )}
    </div>
  );
}
