import { describe, expect, it } from "vitest";
import { parseLoginSetupInput, toView } from "./login-setups";

const form = {
  targetUrl: "https://staging.example.com/app",
  kind: "form",
  loginUrl: "https://staging.example.com/login",
  username: " qa@example.com ",
  password: "s3cret-Pass!",
};

describe("parseLoginSetupInput", () => {
  it("accepts a form login and keys it by the target's origin", () => {
    const parsed = parseLoginSetupInput(form, { passwordSaved: false });
    expect(parsed).toEqual({
      ok: true,
      value: {
        origin: "https://staging.example.com",
        kind: "form",
        loginUrl: "https://staging.example.com/login",
        username: "qa@example.com",
        password: "s3cret-Pass!",
        usernameSelector: null,
        passwordSelector: null,
        submitSelector: null,
        successSelector: null,
        storageState: null,
      },
    });
  });

  it("needs the login page on the same site, a username and (the first time) a password", () => {
    const parsed = parseLoginSetupInput(
      { ...form, loginUrl: "https://evil.test/login", username: "", password: "" },
      { passwordSaved: false },
    );
    expect(parsed).toMatchObject({ ok: false, errors: { loginUrl: expect.any(String), username: expect.any(String), password: expect.any(String) } });
  });

  it("keeps the saved password when an edit leaves the field empty", () => {
    const parsed = parseLoginSetupInput({ ...form, password: "" }, { passwordSaved: true });
    expect(parsed).toMatchObject({ ok: true, value: { password: null } });
  });

  it("accepts a recorded sign-in (Playwright storage state) and rejects anything else", () => {
    const state = JSON.stringify({ cookies: [{ name: "sid", value: "abc", domain: "staging.example.com", path: "/" }], origins: [] });
    expect(parseLoginSetupInput({ targetUrl: form.targetUrl, kind: "storage_state", storageState: state }, { passwordSaved: false })).toMatchObject({
      ok: true,
      value: { kind: "storage_state", storageState: state, password: null, username: null },
    });
    expect(parseLoginSetupInput({ targetUrl: form.targetUrl, kind: "storage_state", storageState: "{not json" }, { passwordSaved: false })).toMatchObject({
      ok: false,
      errors: { storageState: expect.any(String) },
    });
    expect(parseLoginSetupInput({ targetUrl: form.targetUrl, kind: "storage_state", storageState: '{"cookies": 3}' }, { passwordSaved: false })).toMatchObject({
      ok: false,
    });
  });

  it("rejects targets that aren't http(s) and unknown kinds", () => {
    expect(parseLoginSetupInput({ ...form, targetUrl: "ftp://x" }, { passwordSaved: false })).toMatchObject({ ok: false, errors: { targetUrl: expect.any(String) } });
    expect(parseLoginSetupInput({ ...form, kind: "oauth" }, { passwordSaved: false })).toMatchObject({ ok: false, errors: { kind: expect.any(String) } });
  });
});

describe("toView", () => {
  it("never carries the password or the recorded sign-in, only that they are saved", () => {
    const row = {
      id: "1",
      workspaceId: "w",
      origin: "https://staging.example.com",
      kind: "form",
      loginUrl: "https://staging.example.com/login",
      username: "qa@example.com",
      passwordCiphertext: "v1:CIPHER",
      usernameSelector: null,
      passwordSelector: null,
      submitSelector: null,
      successSelector: "#account",
      storageStateCiphertext: "v1:STATE",
      checkRequestedAt: null,
      lastCheck: { ok: true, detail: "signed in", checkedAt: "2026-11-11T10:00:00.000Z" },
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    const view = toView(row);
    expect(JSON.stringify(view)).not.toContain("CIPHER");
    expect(JSON.stringify(view)).not.toContain("STATE");
    expect(view).toMatchObject({ passwordSaved: true, storageStateSaved: true, username: "qa@example.com", checking: false, lastCheck: { ok: true } });
  });
});
