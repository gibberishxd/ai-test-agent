import { describe, expect, it } from "vitest";
import { ACTIONS, can, canAssign, type Action, type Role } from "./roles";

// The whole table, spelled out: a change to who may do what is a visible change to this test.
const MATRIX: Record<Action, Role[]> = {
  "run.view": ["owner", "admin", "member", "viewer"],
  "run.start": ["owner", "admin", "member"],
  "run.stop": ["owner", "admin", "member"],
  "run.share": ["owner", "admin", "member"],
  "finding.triage": ["owner", "admin", "member"],
  "settings.view": ["owner", "admin", "member", "viewer"],
  "domains.manage": ["owner", "admin"],
  "models.manage": ["owner", "admin"],
  "login_setups.manage": ["owner", "admin"],
  "api_keys.manage": ["owner", "admin"],
  "webhooks.manage": ["owner", "admin"],
  "members.manage": ["owner", "admin"],
  "audit.view": ["owner", "admin"],
  "workspace.transfer": ["owner"],
};

describe("can", () => {
  it.each(Object.entries(MATRIX))("%s is allowed for exactly %j", (action, allowed) => {
    for (const role of ["owner", "admin", "member", "viewer"] as Role[]) {
      expect(can(role, action as Action), `${role} ${action}`).toBe(allowed.includes(role));
    }
  });

  it("covers every action, and visitors (no role) can do none of them", () => {
    expect([...ACTIONS].sort()).toEqual(Object.keys(MATRIX).sort());
    for (const action of ACTIONS) expect(can(null, action)).toBe(false);
  });
});

describe("canAssign", () => {
  it("admins hand out admin, member and viewer; only the owner touches the owner", () => {
    expect(canAssign("admin", "member", "viewer")).toBe(true);
    expect(canAssign("admin", "viewer", "admin")).toBe(true);
    expect(canAssign("admin", "member", "owner")).toBe(false);
    expect(canAssign("admin", "owner", "member")).toBe(false); // can't demote the owner
    expect(canAssign("member", "viewer", "member")).toBe(false);
    expect(canAssign("owner", "admin", "member")).toBe(true);
  });
});
