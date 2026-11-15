import { describe, expect, it } from "vitest";
import { acceptAdd } from "./addToCart";

// Run 7, benchmark v2: a double click on "Add to cart" added the quantity twice (both builds).
// The second click of a double click is ignored; a later, deliberate click still adds again.
describe("add to cart clicks", () => {
  it("ignores the second click of a double click", () => {
    expect(acceptAdd(null, 1000)).toBe(true);
    expect(acceptAdd(1000, 1150)).toBe(false);
  });

  it("adds again on a later click", () => {
    expect(acceptAdd(1000, 1000 + 2000)).toBe(true);
  });
});
