import { describe, expect, it } from "vitest";
import { nameError } from "./profile";

describe("nameError", () => {
  it("rejects an empty or blank display name", () => {
    expect(nameError("")).toBe("Enter a display name.");
    expect(nameError("   ")).toBe("Enter a display name.");
  });

  it("accepts any other name", () => {
    expect(nameError("Test User")).toBeUndefined();
  });
});
