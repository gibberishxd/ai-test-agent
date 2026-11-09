"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { startRun } from "@/components/run-form";
import { Button } from "@/components/ui/button";

/** Starts a real interactive run on the demo shop and opens its live page. */
export function TryDemoButton({ demoUrl }: { demoUrl: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    const result = await startRun({ targetUrl: demoUrl, mode: "interactive" });
    if ("id" in result) {
      router.push(`/runs/${result.id}`);
    } else {
      toast.error(Object.values(result.errors)[0] ?? "Couldn't start the run.");
      setBusy(false);
    }
  };

  return (
    <Button size="lg" onClick={start} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : null}
      Try it on our demo shop
      {!busy && <ArrowRight />}
    </Button>
  );
}
