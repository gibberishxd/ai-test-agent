"use client";

import { CheckCircle2, Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Domain = { id: string; hostname: string; verifiedAt: string | null; method: string | null };

export function DomainList({ domains, token }: { domains: Domain[]; token: string }) {
  const router = useRouter();
  const [hostname, setHostname] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("add");
    const response = await fetch("/api/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hostname }),
    });
    const data = await response.json();
    setBusy(null);
    if (!response.ok) return toast.error(data.error);
    setHostname("");
    router.refresh();
  };

  const verify = async (id: string) => {
    setBusy(id);
    const response = await fetch(`/api/domains/${id}/verify`, { method: "POST" });
    const data = await response.json();
    setBusy(null);
    if (!response.ok) return toast.error(data.error);
    toast.success("Domain verified");
    router.refresh();
  };

  return (
    <div className="grid gap-5">
      <ol className="grid list-decimal gap-2 pl-5 text-sm text-muted-foreground">
        <li>Add your domain below.</li>
        <li>
          Prove you own it, one of two ways:
          <ul className="mt-1 grid list-disc gap-1 pl-5">
            <li>
              a DNS TXT record on the domain with the value{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs break-all text-foreground">ai-test-agent-verification={token}</code>
            </li>
            <li>
              or a file at <code className="rounded bg-muted px-1 py-0.5 text-xs">/.well-known/ai-test-agent.txt</code> containing{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs break-all text-foreground">{token}</code>
            </li>
          </ul>
        </li>
        <li>Click Verify. Interactive tests are then allowed on that domain.</li>
      </ol>

      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="grid min-w-56 flex-1 gap-2">
          <Label htmlFor="hostname">Domain</Label>
          <Input id="hostname" placeholder="shop.example.com" value={hostname} onChange={(e) => setHostname(e.target.value)} />
        </div>
        <Button type="submit" disabled={busy !== null || !hostname}>
          {busy === "add" ? <Loader2 className="animate-spin" /> : <Plus />} Add domain
        </Button>
      </form>

      {domains.length === 0 ? (
        <p className="text-sm text-muted-foreground">No domains yet.</p>
      ) : (
        <ul className="grid gap-2">
          {domains.map((domain) => (
            <li key={domain.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
              <span className="font-medium">{domain.hostname}</span>
              {domain.verifiedAt ? (
                <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                  <CheckCircle2 /> Verified ({domain.method === "dns" ? "DNS" : "file"})
                </Badge>
              ) : (
                <Button size="sm" variant="outline" onClick={() => verify(domain.id)} disabled={busy !== null}>
                  {busy === domain.id && <Loader2 className="animate-spin" />} Verify
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
