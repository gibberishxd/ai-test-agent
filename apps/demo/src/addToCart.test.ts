import { describe, expect, it } from "vitest";
import { acceptAdd } from "./addToCart";

// Run 7, benchmark v2: a double click on "Add to cart" added the quantity twice (both builds).
// Only the second click *of a double click* is ignored (the browser marks it detail = 2). Two
// separate clicks add twice, however quickly they come: a replay repeats a user's two clicks
// faster than the user made them (the first version, a 500 ms window, swallowed the second).
describe("add to cart clicks", () => {
  it("ignores the second click of a double click", () => {
    expect(acceptAdd(1)).toBe(true);
    expect(acceptAdd(2)).toBe(false);
    expect(acceptAdd(3)).toBe(false);
  });

  it("adds on every separate click, and on a keyboard press (detail 0)", () => {
    expect(acceptAdd(1)).toBe(true);
    expect(acceptAdd(0)).toBe(true);
  });
});
