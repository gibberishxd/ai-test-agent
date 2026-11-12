/**
 * Who may do what in a workspace (run 4, J5). One table, checked by every route and page through
 * `can` / `forbidden`; the database adds row-level security behind it (docs/DATABASE.md).
 *
 * - owner: everything, including handing ownership to another member.
 * - admin: everything but ownership: members and invitations, API keys, sign-in setups,
 *   webhooks, models, domains, the audit log.
 * - member: start and stop runs, share reports, triage findings.
 * - viewer: read runs, reports and settings (never a secret: those are never readable anyway).
 */
export const ROLES = ["owner", "admin", "member", "viewer"] as const;
export type Role = (typeof ROLES)[number];

const EVERYONE: Role[] = ["owner", "admin", "member", "viewer"];
const MEMBERS: Role[] = ["owner", "admin", "member"];
const ADMINS: Role[] = ["owner", "admin"];

const TABLE = {
  "run.view": EVERYONE,
  "run.start": MEMBERS,
  "run.stop": MEMBERS,
  "run.share": MEMBERS,
  "finding.triage": MEMBERS,
  "settings.view": EVERYONE,
  "domains.manage": ADMINS,
  "models.manage": ADMINS,
  "login_setups.manage": ADMINS,
  "api_keys.manage": ADMINS,
  "webhooks.manage": ADMINS,
  "members.manage": ADMINS,
  "audit.view": ADMINS,
  "workspace.transfer": ["owner"],
} satisfies Record<string, Role[]>;

export type Action = keyof typeof TABLE;
export const ACTIONS = Object.keys(TABLE) as Action[];

/** `role` null: a visitor who isn't signed in (they may only try the demo; see lib/runs.ts). */
export function can(role: Role | null, action: Action): boolean {
  return role !== null && (TABLE[action] as Role[]).includes(role);
}

/** May `actor` change someone's role from `from` to `to`? Ownership only moves by transfer. */
export function canAssign(actor: Role, from: Role, to: Role): boolean {
  if (!can(actor, "members.manage")) return false;
  if (from === "owner" || to === "owner") return false; // see transferOwnership
  return true;
}

/** The 403 a route returns when the role isn't enough. */
export function forbidden(action: Action): Response {
  return Response.json({ error: `Your role in this workspace can't do this (${action}). Ask an admin.` }, { status: 403 });
}
