import { describe, expect, it } from "vitest";
import { clearError, nights, stayTotal, validate } from "./booking";

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
