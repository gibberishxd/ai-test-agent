import { describe, expect, it } from "vitest";
import { isValidTargetUrl } from "./url";

describe("isValidTargetUrl", () => {
  it("accepts http and https", () => {
    expect(isValidTargetUrl("http://localhost:5173")).toBe(true);
    expect(isValidTargetUrl("https://example.com/shop")).toBe(true);
  });

  it("rejects other schemes and garbage", () => {
    expect(isValidTargetUrl("file:///etc/passwd")).toBe(false);
    expect(isValidTargetUrl("javascript:alert(1)")).toBe(false);
    expect(isValidTargetUrl("not a url")).toBe(false);
  });
});
