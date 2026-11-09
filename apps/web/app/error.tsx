"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Shown when a page throws, e.g. the database isn't reachable. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-24 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10">
        <TriangleAlert className="size-6 text-destructive" />
      </span>
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="text-muted-foreground">
        The page couldn&apos;t load. If you&apos;re running locally, check that Postgres is up
        (<code>npm run db:up</code>).
      </p>
      {error.digest && <p className="text-xs text-muted-foreground">Error id: {error.digest}</p>}
      <Button onClick={reset}>
        <RotateCcw /> Try again
      </Button>
    </main>
  );
}
