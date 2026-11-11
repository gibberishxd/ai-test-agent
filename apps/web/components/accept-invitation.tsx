"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function AcceptInvitation({ token }: { token: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const accept = async () => {
    setBusy(true);
    const response = await fetch("/api/invitations/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    setBusy(false);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) return toast.error(data.error ?? "Couldn't join.");
    toast.success("You've joined the workspace.");
    router.push("/dashboard");
  };
  return (
    <Button onClick={accept} disabled={busy}>
      {busy && <Loader2 className="animate-spin" />} Join workspace
    </Button>
  );
}
