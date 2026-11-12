import { describe, expect, it, vi } from "vitest";
import { checkEndpoint, probeModel, type HttpReply, type PostJson, type ProbeDeps, type ProbeTarget } from "./model-probe";

const NOW = new Date("2026-11-10T12:00:00Z");
const KEY = "sk-live-ABCD1234wxyz";
const OPENAI: ProbeTarget = { provider: "openai-compat", baseUrl: "https://api.example.test/v1/", model: "m", apiKey: KEY };

function deps(replies: HttpReply[], overrides: Partial<Omit<ProbeDeps, "post">> = {}) {
  const post = vi.fn<PostJson>(async () => replies.shift()!);
  return { resolveIps: async () => ["93.184.215.14"], devMode: false, ...overrides, post };
}

const toolCall = { status: 200, body: { choices: [{ message: { tool_calls: [{ function: { name: "record_answer" } }] } }] } };
const saysRed = { status: 200, body: { choices: [{ message: { content: "Red." } }] } };

describe("probeModel (OpenAI-compatible)", () => {
  it("passes a model that calls tools and reads images", async () => {
    const d = deps([toolCall, saysRed]);
    const result = await probeModel(OPENAI, d, NOW);
    expect(result).toEqual({ ok: true, answers: true, tools: true, vision: true, error: null, checkedAt: NOW.toISOString() });
    const [url, headers, body] = d.post.mock.calls[0]! as [string, Record<string, string>, { tools: unknown[] }];
    expect(url).toBe("https://api.example.test/v1/chat/completions");
    expect(headers.Authorization).toBe(`Bearer ${KEY}`);
    expect(body.tools).toHaveLength(1);
    const imageBody = d.post.mock.calls[1]![2] as { messages: { content: { type: string }[] }[] };
    expect(imageBody.messages[0]!.content[0]!.type).toBe("image_url");
  });

  it("fails a model without tool calling, with a reason", async () => {
    const result = await probeModel(OPENAI, deps([{ status: 200, body: { choices: [{ message: { content: "ok" } }] } }, saysRed]), NOW);
    expect(result).toMatchObject({ ok: false, answers: true, tools: false, vision: true });
    expect(result.error).toMatch(/tool calling/);
  });

  it("fails a text-only model that doesn't see the image", async () => {
    const blind = { status: 200, body: { choices: [{ message: { content: "I can't see images." } }] } };
    const result = await probeModel(OPENAI, deps([toolCall, blind]), NOW);
    expect(result).toMatchObject({ ok: false, tools: true, vision: false });
    expect(result.error).toMatch(/image input/);
  });

  it("reports an HTTP error without ever repeating the key", async () => {
    const refused = { status: 401, body: { error: { message: `Incorrect API key provided: ${KEY}` } } };
    const result = await probeModel(OPENAI, deps([refused]), NOW);
    expect(result.ok).toBe(false);
    expect(result.error).toContain("HTTP 401");
    expect(result.error).not.toContain(KEY);
  });

  it("sends no Authorization header to a keyless local server", async () => {
    const d = deps([toolCall, saysRed], { devMode: true, resolveIps: async () => ["127.0.0.1"] });
    await probeModel({ ...OPENAI, baseUrl: "http://localhost:11434/v1", apiKey: null }, d, NOW);
    expect(d.post.mock.calls[0]![1]).toEqual({});
  });
});

describe("probeModel (Anthropic)", () => {
  it("uses the Messages API with the key in x-api-key", async () => {
    const tool = { status: 200, body: { content: [{ type: "tool_use", name: "record_answer" }] } };
    const red = { status: 200, body: { content: [{ type: "text", text: "Red" }] } };
    const d = deps([tool, red]);
    const result = await probeModel({ provider: "claude", baseUrl: null, model: "claude-haiku-5-5", apiKey: KEY }, d, NOW);
    expect(result.ok).toBe(true);
    expect(d.post.mock.calls[0]![0]).toBe("https://api.anthropic.com/v1/messages");
    expect(d.post.mock.calls[0]![1]).toMatchObject({ "x-api-key": KEY });
  });
});

describe("checkEndpoint (SSRF)", () => {
  const privateHost = { resolveIps: async () => ["10.0.0.5"], devMode: false };

  it("refuses a base URL that resolves to a private address, before any request", async () => {
    const post = vi.fn<PostJson>();
    const result = await probeModel(OPENAI, { ...privateHost, post }, NOW);
    expect(result.error).toMatch(/private address/);
    expect(post).not.toHaveBeenCalled();
  });

  it("allows a local server only in dev mode", async () => {
    const local = { ...OPENAI, baseUrl: "http://localhost:1234/v1" };
    expect((await checkEndpoint(local, { resolveIps: async () => ["127.0.0.1"], devMode: false })).ok).toBe(false);
    expect((await checkEndpoint(local, { resolveIps: async () => ["127.0.0.1"], devMode: true })).ok).toBe(true);
  });

  it("refuses URLs that aren't http(s)", async () => {
    const result = await checkEndpoint({ ...OPENAI, baseUrl: "file:///etc/passwd" }, privateHost);
    expect(result).toMatchObject({ ok: false });
  });
});
