import { describe, expect, it } from "vitest";
import { isDemoTarget, parseRunInput, sameOrigin } from "./targets";

describe("parseRunInput", () => {
  it("accepts a public URL in passive mode", () => {
    const result = parseRunInput({ targetUrl: " https://example.com ", mode: "passive", focus: "" });
    expect(result).toEqual({
      ok: true,
      value: { targetUrl: "https://example.com/", mode: "passive", focus: null },
    });
  });

  it("rejects non-http schemes", () => {
    const result = parseRunInput({ targetUrl: "file:///etc/passwd", mode: "passive" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.targetUrl).toMatch(/http/);
  });

  it("rejects an empty URL with a helpful message", () => {
    const result = parseRunInput({ targetUrl: "", mode: "passive" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.targetUrl).toBe("Enter the URL of the app to test.");
  });

  it("allows interactive mode on the demo shop", () => {
    expect(parseRunInput({ targetUrl: "http://localhost:5173/", mode: "interactive" }).ok).toBe(true);
  });

  it("refuses interactive mode on an unverified domain", () => {
    const result = parseRunInput({ targetUrl: "https://example.com", mode: "interactive" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.mode).toMatch(/verified/);
  });

  it("allows interactive mode on a verified domain", () => {
    const result = parseRunInput({ targetUrl: "https://example.com/app", mode: "interactive" }, [
      "https://example.com",
    ]);
    expect(result.ok).toBe(true);
  });

  it("limits the focus length", () => {
    const result = parseRunInput({
      targetUrl: "https://a.test",
      mode: "passive",
      focus: "x".repeat(301),
    });
    expect(result.ok).toBe(false);
  });
});

describe("origins", () => {
  it("compares scheme, host and port", () => {
    expect(sameOrigin("http://localhost:5173/cart", "http://localhost:5173")).toBe(true);
    expect(sameOrigin("http://localhost:5174", "http://localhost:5173")).toBe(false);
  });

  it("knows both demo shops", () => {
    expect(isDemoTarget("http://localhost:5173/products/1")).toBe(true);
    expect(isDemoTarget("http://localhost:5174/")).toBe(true);
    expect(isDemoTarget("https://example.com")).toBe(false);
  });
});
