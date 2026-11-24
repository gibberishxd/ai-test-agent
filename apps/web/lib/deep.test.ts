import { describe, expect, it } from "vitest";
import { MAX_DEEP_MINUTES, MAX_DEEP_STEPS, parseDeepLimits } from "./deep";

describe("parseDeepLimits (run 9)", () => {
  it("takes whole numbers, or empty for the product default", () => {
    expect(parseDeepLimits({ steps: "800", minutes: 90 })).toEqual({ ok: true, value: { steps: 800, minutes: 90 } });
    expect(parseDeepLimits({ steps: "", minutes: null })).toEqual({ ok: true, value: { steps: null, minutes: null } });
  });

  it("refuses anything else, saying the range", () => {
    expect(parseDeepLimits({ steps: 0 })).toMatchObject({ ok: false, errors: { steps: expect.stringContaining(String(MAX_DEEP_STEPS)) } });
    expect(parseDeepLimits({ minutes: MAX_DEEP_MINUTES + 1 })).toMatchObject({ ok: false, errors: { minutes: expect.any(String) } });
    expect(parseDeepLimits({ steps: "1.5" })).toMatchObject({ ok: false });
  });
});
