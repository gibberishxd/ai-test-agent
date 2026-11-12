import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { DomainList } from "@/components/domain-list";
import { IntegrationSettings } from "@/components/integration-settings";
import { LoginSettings } from "@/components/login-settings";
import { ModelSettings } from "@/components/model-settings";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MembersSettings } from "@/components/members-settings";
import { listInvitations, listMembers } from "@/lib/members";
import { can } from "@/lib/roles";
import { currentContext } from "@/lib/workspace";
import { db } from "@/lib/db";
import { tenantDb } from "@/lib/tenant-db";
import { formatCost, formatDate, hostOf } from "@/lib/format";
import { listApiKeys } from "@/lib/api-keys";
import { listLoginSetups } from "@/lib/login-setups";
import { listWebhooks } from "@/lib/webhooks";
import { listModelConfigs } from "@/lib/model-configs";
import { auditLog, listDomains, usageThisMonth } from "@/lib/settings-data";

export const metadata: Metadata = { title: "Settings" };

const ACTIONS: Record<string, string> = {
  "run.started": "Started a run",
  "domain.verified": "Verified a domain",
  "share.created": "Shared a report",
  "share.revoked": "Revoked a share link",
  "model.added": "Added a model",
  "model.key_replaced": "Replaced a model's key",
  "model.deleted": "Deleted a model",
  "model.tested": "Tested a model connection",
};

export default async function SettingsPage() {
  const context = await currentContext();
  const userEmail = context.userId ? (await db.user.findUnique({ where: { id: context.userId } }))?.email : null;
  const user = context.signedIn && context.userId ? { id: context.userId, workspaceId: context.workspaceId, email: userEmail ?? "" } : null;
  const role = context.role ?? "viewer";
  const admin = can(role, "members.manage");
  const readOnly = <p className="text-sm text-muted-foreground">Only owners and admins can change this.</p>;
  if (!user) redirect("/signin");

  const [workspace, domains, usage, log, models, loginSetups, apiKeys, webhooks, members, invitations] = await Promise.all([
    tenantDb(user.workspaceId).workspace.findUniqueOrThrow({ where: { id: user.workspaceId } }),
    listDomains(user.workspaceId),
    usageThisMonth(user.workspaceId),
    auditLog(user.workspaceId),
    listModelConfigs(user.workspaceId),
    listLoginSetups(user.workspaceId),
    listApiKeys(user.workspaceId),
    listWebhooks(user.workspaceId),
    listMembers(user.workspaceId),
    admin ? listInvitations(user.workspaceId) : Promise.resolve([]),
  ]);
  const used = Math.min(usage.runs / usage.quota, 1);

  return (
    <main className="mx-auto grid max-w-4xl gap-8 px-4 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-muted-foreground">Signed in as {user.email}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>
            You are {role === "owner" ? "the owner" : `a${role === "admin" ? "n" : ""} ${role}`} of this workspace.{" "}
            <Link href="/settings/usage" className="underline">
              Plan and usage
            </Link>
            {admin && (
              <>
                {" "}
                <Link href="/settings/audit" className="underline">
                  Full audit log
                </Link>
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MembersSettings members={members} invitations={invitations} me={user.id} myRole={role} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Usage this month</CardTitle>
          <CardDescription>
            {usage.runs} of {usage.quota} runs · {formatCost(usage.costUsd)} spent on AI models
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div
            className="h-2 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={usage.quota}
            aria-valuenow={usage.runs}
            aria-label="Runs used this month"
          >
            <div className="h-full rounded-full bg-primary" style={{ width: `${used * 100}%` }} />
          </div>
          {usage.byProvider.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead className="text-right">Runs</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usage.byProvider.map((row) => (
                  <TableRow key={row.provider}>
                    <TableCell>{row.provider}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.runs}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCost(row.costUsd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Models</CardTitle>
          <CardDescription>
            Bring any model: an OpenAI-compatible endpoint (OpenAI, Gemini, OpenRouter, Groq, LM Studio, vLLM,
            Ollama) or an Anthropic key. The agent needs tool calling and image input, which Test connection
            checks. See how each model scores on the <Link href="/benchmark" className="underline">benchmark</Link>{" "}
            before you rely on it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {admin ? <ModelSettings models={models} /> : readOnly}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Domains for interactive tests</CardTitle>
          <CardDescription>
            Interactive tests type into forms and click buttons, so they only run on domains you
            prove you own. Passive scans work on any public URL.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {admin ? (
          <DomainList
            token={workspace.verificationToken}
            domains={domains.map((d) => ({
              id: d.id,
              hostname: d.hostname,
              verifiedAt: d.verifiedAt?.toISOString() ?? null,
              method: d.method,
            }))}
          />
          ) : (
            readOnly
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sign-in for apps behind a login</CardTitle>
          <CardDescription>
            For a verified domain, the worker can sign in with a test account before the agent starts, so the
            agent tests what signed-in users see. The password is stored encrypted and never reaches the AI model.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {admin ? <LoginSettings setups={loginSetups} /> : readOnly}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>CI integration</CardTitle>
          <CardDescription>
            Start runs from your pipeline with an API key, get the report as JSON or JUnit XML, and receive a signed
            webhook when a run finishes. Examples for GitHub Actions are in <code>examples/ci</code>; the API contract
            is at <a className="underline" href="/api/v1/openapi.json">/api/v1/openapi.json</a>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {admin ? <IntegrationSettings keys={apiKeys} webhooks={webhooks} /> : readOnly}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>Who did what in this workspace, newest first.</CardDescription>
        </CardHeader>
        <CardContent>
          {log.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Who</TableHead>
                    <TableHead>What</TableHead>
                    <TableHead>Target</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {log.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-muted-foreground">{formatDate(entry.createdAt)}</TableCell>
                      <TableCell>{entry.user?.email ?? "visitor"}</TableCell>
                      <TableCell>
                        {ACTIONS[entry.action] ?? entry.action}
                        {entry.mode ? ` (${entry.mode})` : ""}
                      </TableCell>
                      <TableCell className="max-w-48 truncate">
                        {entry.runId ? (
                          <Link href={`/runs/${entry.runId}`} className="hover:underline">
                            {entry.targetUrl ? hostOf(entry.targetUrl) : "run"}
                          </Link>
                        ) : entry.targetUrl ? (
                          hostOf(entry.targetUrl)
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
