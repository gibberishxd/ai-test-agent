import { describe, expect, it } from "vitest";
import { CLAUDE_MODELS, modelForProvider, parseModelInput } from "./model-configs";

describe("parseModelInput", () => {
  it("accepts an OpenAI-compatible endpoint", () => {
    const parsed = parseModelInput({ label: " Groq ", provider: "openai-compat", baseUrl: "https://api.groq.test/openai/v1", model: "llama-5", apiKey: "gsk_1" });
    expect(parsed).toEqual({
      ok: true,
      value: { label: "Groq", provider: "openai-compat", baseUrl: "https://api.groq.test/openai/v1", model: "llama-5", cheapModel: null, apiKey: "gsk_1", inputPrice: 0, outputPrice: 0 },
    });
  });

  it("needs a base URL for OpenAI-compatible, and a key for Anthropic", () => {
    expect(parseModelInput({ label: "x", provider: "openai-compat", model: "m" })).toMatchObject({ ok: false, errors: { baseUrl: expect.any(String) } });
    expect(parseModelInput({ label: "x", provider: "claude", model: "claude-haiku-5-5" })).toMatchObject({ ok: false, errors: { apiKey: expect.any(String) } });
  });

  it("offers only providers a workspace may use (never the local claude-cli)", () => {
    expect(parseModelInput({ label: "x", provider: "claude-cli", model: "sonnet" })).toMatchObject({ ok: false, errors: { provider: expect.any(String) } });
  });

  it("rejects negative or non-numeric prices", () => {
    const parsed = parseModelInput({ label: "x", provider: "openai-compat", baseUrl: "https://a.test/v1", model: "m", inputPrice: "-1" });
    expect(parsed).toMatchObject({ ok: false, errors: { inputPrice: expect.any(String) } });
  });
});

describe("Claude model suggestions (run 7: Haiku is the default, D91)", () => {
  it("offers Haiku first as the recommended default and Sonnet as the thorough option", () => {
    expect(CLAUDE_MODELS.map((m) => m.id)).toEqual(["claude-haiku-5-5", "claude-sonnet-5-5"]);
    expect(CLAUDE_MODELS[0].label).toMatch(/default/i);
    expect(CLAUDE_MODELS[1].label).toMatch(/thorough/i);
  });

  it("fills in Haiku when Claude is picked and no model was typed, and keeps a typed one", () => {
    expect(modelForProvider("claude", "")).toBe("claude-haiku-5-5");
    expect(modelForProvider("claude", "claude-sonnet-5-5")).toBe("claude-sonnet-5-5");
    expect(modelForProvider("openai-compat", "")).toBe("");
  });
});
