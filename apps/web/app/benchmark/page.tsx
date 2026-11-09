import { Gauge } from "lucide-react";
import type { Metadata } from "next";
import { EmptyState } from "@/components/empty-state";

export const metadata: Metadata = { title: "Benchmark" };

// Replaced in M7 by the real benchmark page (scores per provider, per-bug table, chart).
export default function BenchmarkPage() {
  return (
    <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1>
      <EmptyState icon={Gauge} title="No benchmark results yet">
        Run <code>npm run bench</code> to measure recall, precision, false alarms and cost.
      </EmptyState>
    </main>
  );
}
