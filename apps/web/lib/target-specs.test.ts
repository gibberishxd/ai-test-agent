import { describe, expect, it } from "vitest";
import { MAX_SPEC_CHARS, parseSpecInput, parseTargetInput, specStatus } from "./target-specs";
import { violatedSpec } from "./spec-citation";

describe("parseTargetInput (run 7)", () => {
  it("keeps only the origin of the URL a team pastes", () => {
    expect(parseTargetInput({ url: " https://staging.example.com/app/login?x=1 ", name: " Staging " })).toEqual({
      ok: true,
      value: { origin: "https://staging.example.com", name: "Staging" },
    });
    expect(parseTargetInput({ url: "http://localhost:5175" })).toEqual({ ok: true, value: { origin: "http://localhost:5175", name: null } });
  });

  it("refuses what isn't an http(s) URL", () => {
    expect(parseTargetInput({ url: "ftp://x.test" })).toEqual({ ok: false, errors: { url: expect.any(String) } });
    expect(parseTargetInput({ url: "" })).toEqual({ ok: false, errors: { url: expect.any(String) } });
  });
});

describe("parseSpecInput (run 7)", () => {
  it("accepts a title and a Markdown or text body", () => {
    expect(parseSpecInput({ title: " Booking ", body: "## Dates\n- Check-in before check-out." })).toEqual({
      ok: true,
      value: { title: "Booking", body: "## Dates\n- Check-in before check-out." },
    });
  });

  it("needs both, and caps the body", () => {
    const missing = parseSpecInput({ title: "", body: " " });
    expect(missing.ok).toBe(false);
    if (!missing.ok) expect(Object.keys(missing.errors).sort()).toEqual(["body", "title"]);
    const long = parseSpecInput({ title: "Big", body: "x".repeat(MAX_SPEC_CHARS + 1) });
    expect(long.ok).toBe(false);
  });
});

describe("specStatus (run 7)", () => {
  const at = (iso: string) => new Date(iso);
  it("is ready once the worker has embedded the latest version, waiting before", () => {
    expect(specStatus({ chunkedAt: null, updatedAt: at("2026-11-16T10:00:00Z") })).toBe("waiting");
    expect(specStatus({ chunkedAt: at("2026-11-16T09:00:00Z"), updatedAt: at("2026-11-16T10:00:00Z") })).toBe("waiting");
    expect(specStatus({ chunkedAt: at("2026-11-16T10:00:00Z"), updatedAt: at("2026-11-16T10:00:00Z") })).toBe("ready");
  });
});

describe("violatedSpec (run 7)", () => {
  it("reads the requirement a finding breaks from its evidence", () => {
    const evidence = { spec: { label: "S2", spec_id: "s", chunk_id: "c", title: "Booking", heading: "Booking > Dates" } };
    expect(violatedSpec(evidence)).toEqual({ title: "Booking", heading: "Booking > Dates" });
    expect(violatedSpec({})).toBeNull();
    expect(violatedSpec({ spec: "nonsense" })).toBeNull();
  });
});
