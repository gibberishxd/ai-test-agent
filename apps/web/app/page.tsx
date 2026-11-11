import { CheckCircle2, Link2, ScanSearch, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { connection } from "next/server";
import { TryDemoButton } from "@/components/try-demo-button";
import { Button } from "@/components/ui/button";
import { validResults } from "@/lib/benchmark";
import { db } from "@/lib/db";
import { formatCost } from "@/lib/format";
import { demoUrl } from "@/lib/targets";

const STEPS = [
  {
    icon: Link2,
    title: "Paste a URL",
    text: "No SDK, no code access. A passive scan is safe on any public site.",
  },
  {
    icon: ScanSearch,
    title: "The agent tests it",
    text: "Automatic checks on every page, then an AI agent walks your flows like a QA tester.",
  },
  {
    icon: CheckCircle2,
    title: "Get bugs you can trust",
    text: "Each model-reported bug is replayed in a fresh browser before it reaches your report.",
  },
];

const FAQ = [
  {
    q: "Is it safe to point at my production site?",
    a: "Passive scans only load pages and follow links: no typing, no form submits, no button clicks. Interactive tests run only on domains you've verified. A deny list blocks payments, deletes, sends and account changes, and the worker never reaches private or internal network addresses. Every blocked action is shown in the run timeline.",
  },
  {
    q: "What does a run cost?",
    a: "Automatic checks are free. The AI model reads a compact text view of each page and sees screenshots only when needed, with prompt caching. Every run has a hard cost cap (default $1.00), and cost per run is shown on every report and on the benchmark page.",
  },
  {
    q: "How do you know the bugs are real?",
    a: "Automatic checks come with hard evidence: console errors, failed requests, accessibility violations. Bugs the model reports are replayed step by step in a fresh browser and dismissed if they don't reproduce. The benchmark page shows how often the agent finds planted bugs and how often it raises false alarms.",
  },
  {
    q: "Can the site I test take over the agent?",
    a: "Page content is treated as untrusted data. It reaches the model in a clearly fenced block, and the agent's tools can only act inside the browser on the target site. Our demo shop contains text telling the agent to report no bugs; it's part of our tests.",
  },
];

async function latestBenchmark() {
  try {
    // The newest result that counts (an invalid one is kept but not shown).
    const newest = await db.benchmarkResult.findMany({ orderBy: { createdAt: "desc" }, take: 10 });
    return validResults(newest)[0] ?? null;
  } catch {
    return null;
  }
}

export default async function LandingPage() {
  await connection();
  const benchmark = await latestBenchmark();

  return (
    <main>
      <section className="mx-auto grid max-w-6xl gap-6 px-4 pt-20 pb-16 text-center sm:pt-28">
        <p className="mx-auto w-fit rounded-full border px-3 py-1 text-sm text-muted-foreground">
          AI QA for teams that ship weekly
        </p>
        <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          Paste a URL. Get a bug report you can act on.
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-muted-foreground text-balance">
          An AI agent explores your web app like a manual tester and reports bugs with severity,
          screenshots, repro steps and console evidence, in minutes.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <TryDemoButton demoUrl={demoUrl()} />
          <Button size="lg" variant="outline" asChild>
            <Link href="/dashboard">Test your own app</Link>
          </Button>
        </div>
      </section>

      <section className="border-y bg-muted/30">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="grid gap-2">
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="size-5" />
              </span>
              <h2 className="font-semibold">
                {i + 1}. {title}
              </h2>
              <p className="text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-4 py-16">
        <div className="grid gap-2">
          <h2 className="text-2xl font-semibold tracking-tight">Measured, not promised</h2>
          <p className="max-w-2xl text-muted-foreground">
            The agent is benchmarked against a demo shop with 12 planted bugs and a clean copy with
            none. These are the latest numbers.
          </p>
        </div>
        {benchmark ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Recall" value={`${Math.round(benchmark.recall * 100)}%`} hint="planted bugs found" />
            <Metric label="Precision" value={`${Math.round(benchmark.precision * 100)}%`} hint="reports that were real" />
            <Metric label="False alarms" value={benchmark.falseAlarms.toFixed(1)} hint="per run on the clean shop" />
            <Metric label="Cost per run" value={formatCost(benchmark.avgCostUsd)} hint={`${benchmark.provider} · ${benchmark.model}`} />
          </div>
        ) : (
          <p className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No benchmark results yet. Run <code>npm run bench</code> to produce the first ones.
          </p>
        )}
        <Link href="/benchmark" className="w-fit text-sm font-medium text-primary hover:underline">
          See the full benchmark
        </Link>
      </section>

      <section className="border-t">
        <div className="mx-auto grid max-w-3xl gap-6 px-4 py-16">
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <ShieldCheck className="size-6 text-primary" /> Questions
          </h2>
          <dl className="grid gap-6">
            {FAQ.map(({ q, a }) => (
              <div key={q} className="grid gap-1">
                <dt className="font-medium">{q}</dt>
                <dd className="text-muted-foreground">{a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-muted-foreground">
          AI Test Agent · a portfolio project. Built with Next.js, Python, Playwright and Claude.
        </div>
      </footer>
    </main>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
