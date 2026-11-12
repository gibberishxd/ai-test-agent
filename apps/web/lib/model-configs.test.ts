import { describe, expect, it } from "vitest";
import { parseModelInput } from "./model-configs";

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
