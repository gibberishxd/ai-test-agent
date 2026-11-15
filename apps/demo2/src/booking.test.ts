import { describe, expect, it } from "vitest";
import { clearError, nights, openWindow, stayTotal, validate } from "./booking";

// Vitest runs in "test" mode, so bug(n) is on here: these tests pin the buggy behaviour
// (verify-bugs then checks both builds in a browser) and the parts no bug touches.
describe("booking", () => {
  it("counts nights between dates", () => {
    expect(nights("2027-01-10", "2027-01-13")).toBe(3);
    expect(nights("2027-01-10", "2027-01-09")).toBe(-1);
    expect(nights("", "2027-01-09")).toBe(0);
  });

  it("has the planted total bug in the buggy build", () => {
    expect(stayTotal(120, 3)).toBe(120);
    expect(stayTotal(120, 0)).toBe(0);
  });

  it("rejects a missing name, a bad email and missing dates", () => {
    const errors = validate({ guest: " ", email: "ada@", checkIn: "", checkOut: "" });
    expect(Object.keys(errors).sort()).toEqual(["checkIn", "checkOut", "email", "guest"]);
  });

  it("clears a field's error once that field is edited, keeping the others", () => {
    const errors = { checkOut: "Check-out must be after check-in.", email: "Enter a valid email address." };
    expect(clearError(errors, "checkOut")).toEqual({ email: "Enter a valid email address." });
    expect(clearError(errors, "guest")).toEqual(errors);
  });
});

// Run 7, benchmark v2: two unplanted behaviours that run 6's agents reported, fixed in both builds.
describe("booking dates (benchmark v2)", () => {
  const form = { guest: "Ada", email: "ada@example.com", checkIn: "2027-01-10", checkOut: "2027-01-13" };
  const today = "2026-11-15";

  it("refuses a check-in date in the past", () => {
    const errors = validate({ ...form, checkIn: "2026-11-14", checkOut: "2026-11-16" }, { today });
    expect(errors.checkIn).toMatch(/past/i);
    expect(validate({ ...form, checkIn: today, checkOut: "2026-11-16" }, { today }).checkIn).toBeUndefined();
  });

  it("refuses dates outside the room's availability when it is known", () => {
    const open = { from: "2027-01-05", to: "2027-03-31" };
    expect(validate({ ...form, checkIn: "2027-01-02", checkOut: "2027-01-06" }, { today, open }).checkIn).toMatch(/open from/i);
    expect(validate({ ...form, checkIn: "2027-03-30", checkOut: "2027-04-02" }, { today, open }).checkOut).toMatch(/open from/i);
    expect(validate(form, { today, open })).toEqual({});
  });

  it("can't check the window when availability is unknown, so it doesn't block the booking", () => {
    // The buggy build's availability API fails on purpose (planted bug 1): the form must stay
    // usable there, or the planted booking bugs behind it couldn't be reached.
    expect(validate(form, { today, open: null })).toEqual({});
  });

  it("parses the availability API's answer", () => {
    expect(openWindow({ openFrom: "2027-01-05", openTo: "2027-03-31" })).toEqual({ from: "2027-01-05", to: "2027-03-31" });
    expect(openWindow({ error: "Service Unavailable" })).toBeNull();
  });
});
