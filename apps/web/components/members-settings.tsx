"use client";

import { Copy, Crown, Loader2, Trash2, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { InvitationView, MemberView } from "@/lib/members";
import { ROLES, type Role } from "@/lib/roles";

/**
 * Members and invitation links. Admins invite (the link is shown once: copy it and send it
 * yourself), change roles and remove members; only the owner hands over ownership.
 */
export function MembersSettings({
  members,
  invitations,
  me,
  myRole,
}: {
  members: MemberView[];
  invitations: InvitationView[];
  me: string;
  myRole: Role;
}) {
  const router = useRouter();
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const manage = myRole === "owner" || myRole === "admin";

  async function call(path: string, method: string, body?: unknown, success?: string) {
    setBusy(path + method);
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    setBusy(null);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      toast.error(data.error ?? "Something went wrong.");
      return null;
    }
    if (success) toast.success(success);
    router.refresh();
    return data;
  }

  const invite = async () => {
    const data = await call("/api/invitations", "POST", { role: inviteRole });
    if (data) setLink(data.link);
  };

  return (
    <div className="grid gap-4">
      <ul className="grid gap-2" data-testid="member-list">
        {members.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
            <span className="font-medium">{m.name ?? m.email}</span>
            <span className="text-muted-foreground">{m.email}</span>
            {m.id === me && <Badge variant="outline">you</Badge>}
            <div className="ml-auto flex items-center gap-2">
              {manage && m.role !== "owner" && m.id !== me ? (
                <select
                  aria-label={`Role of ${m.email}`}
                  value={m.role}
                  onChange={(e) => call(`/api/members/${m.id}`, "PATCH", { role: e.target.value }, "Role changed.")}
                  className="h-8 rounded-md border bg-transparent px-2 text-sm"
                >
                  {ROLES.filter((r) => r !== "owner").map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              ) : (
                <Badge variant={m.role === "owner" ? "default" : "outline"}>{m.role}</Badge>
              )}
              {myRole === "owner" && m.id !== me && (
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => call(`/api/members/${m.id}/owner`, "POST", undefined, "Ownership transferred.")}>
                  <Crown /> Make owner
                </Button>
              )}
              {manage && m.role !== "owner" && m.id !== me && (
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => call(`/api/members/${m.id}`, "DELETE", undefined, "Member removed.")}>
                  <Trash2 /> Remove
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {manage && (
        <div className="grid gap-3 rounded-lg border p-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid gap-1 text-sm">
              Invite as
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)} className="h-9 rounded-md border bg-transparent px-2 text-sm">
                <option value="admin">admin</option>
                <option value="member">member</option>
                <option value="viewer">viewer</option>
              </select>
            </label>
            <Button onClick={invite} disabled={busy !== null}>
              {busy === "/api/invitationsPOST" ? <Loader2 className="animate-spin" /> : <UserPlus />} Create invitation link
            </Button>
          </div>
          {link && (
            <div className="flex gap-2" data-testid="invite-link">
              <code className="flex-1 overflow-x-auto rounded bg-muted px-2 py-1.5 text-xs break-all">{link}</code>
              <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(link).then(() => toast.success("Copied."))}>
                <Copy /> Copy
              </Button>
            </div>
          )}
          <p className="text-xs text-muted-foreground">No email is sent: copy the link and send it yourself. It works once and expires in 7 days.</p>
          {invitations.length > 0 && (
            <ul className="grid gap-1 text-sm">
              {invitations.map((inv) => (
                <li key={inv.id} className="flex items-center gap-2">
                  Pending {inv.role} invitation · expires {new Date(inv.expiresAt).toLocaleDateString()}
                  <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => call(`/api/invitations/${inv.id}`, "DELETE", undefined, "Invitation revoked.")}>
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
