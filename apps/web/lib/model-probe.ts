/**
 * "Test connection" for a workspace's model: does the endpoint answer, can the model call a
 * tool, and does it read an image? The agent needs all three, so a model that fails any of
 * them is refused before a run starts, with the reason, instead of failing halfway through.
 *
 * The web server calls a URL the user typed, so the same SSRF rule as domain verification
 * applies: resolve the host, refuse private addresses (allowed only with DEV_MODE=true, for a
 * local Ollama or LM Studio), and connect to exactly the address that was checked.
 */
import { lookup } from "node:dns/promises";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { isPublicIp, pinnedLookup } from "@/lib/domains";

export type ProbeResult = {
  ok: boolean;
  answers: boolean;
  tools: boolean;
  vision: boolean;
  error: string | null;
  checkedAt: string;
};

export type ProbeTarget = {
  provider: string;
  baseUrl: string | null;
  model: string;
  apiKey: string | null;
};

export type HttpReply = { status: number; body: unknown };
export type PostJson = (url: string, headers: Record<string, string>, body: unknown) => Promise<HttpReply>;
export type ProbeDeps = { post: PostJson; resolveIps: (host: string) => Promise<string[]>; devMode: boolean };

export const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

/** A 16×16 solid red PNG: a model that reads images says "red". */
export const RED_PNG =
  "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGO4I2JDEmIY1TCqYfhqAAAeBCwQ8YdREQAAAABJRU5ErkJggg==";

const TOOL = {
  name: "record_answer",
  description: "Record your answer.",
  parameters: { type: "object", properties: { answer: { type: "string" } }, required: ["answer"] },
};

/** The endpoint URL for a model, or an error for one we won't call. */
export async function checkEndpoint(
  target: ProbeTarget,
  deps: Pick<ProbeDeps, "resolveIps" | "devMode">,
): Promise<{ ok: true; url: string } | { ok: false; error: string }> {
  const url =
    target.provider === "claude"
      ? ANTHROPIC_URL
      : `${(target.baseUrl ?? "").replace(/\/+$/, "")}/chat/completions`;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { ok: false, error: "The base URL isn't a valid URL." };
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, error: "The base URL must start with https:// (or http:// for a local server)." };
  }
  const ips = await deps.resolveIps(parsed.hostname).catch(() => []);
  if (ips.length === 0) return { ok: false, error: `Couldn't resolve ${parsed.hostname}.` };
  if (!deps.devMode && !ips.every(isPublicIp)) {
    return { ok: false, error: `${parsed.hostname} points to a private address; only public endpoints are allowed.` };
  }
  return { ok: true, url };
}

/** Mask the key wherever it appears in text (some servers echo it back in errors). */
export function redactKey(text: string, apiKey: string | null): string {
  return apiKey ? text.split(apiKey).join("[REDACTED]") : text;
}

export async function probeModel(target: ProbeTarget, deps: ProbeDeps, now = new Date()): Promise<ProbeResult> {
  const result: ProbeResult = { ok: false, answers: false, tools: false, vision: false, error: null, checkedAt: now.toISOString() };
  const endpoint = await checkEndpoint(target, deps);
  if (!endpoint.ok) return { ...result, error: endpoint.error };
  const claude = target.provider === "claude";
  const headers: Record<string, string> = claude
    ? { "x-api-key": target.apiKey ?? "", "anthropic-version": "2023-06-01" }
    : target.apiKey
      ? { Authorization: `Bearer ${target.apiKey}` }
      : {};

  try {
    const toolReply = await deps.post(endpoint.url, headers, claude ? claudeToolBody(target.model) : openAiToolBody(target.model));
    if (toolReply.status >= 400) {
      return { ...result, error: `The endpoint answered HTTP ${toolReply.status}: ${redactKey(errorText(toolReply.body), target.apiKey)}` };
    }
    result.answers = true;
    result.tools = claude ? claudeCalledTool(toolReply.body) : openAiCalledTool(toolReply.body);

    const imageReply = await deps.post(endpoint.url, headers, claude ? claudeImageBody(target.model) : openAiImageBody(target.model));
    const text = claude ? claudeText(imageReply.body) : openAiText(imageReply.body);
    result.vision = imageReply.status < 400 && /\bred\b/i.test(text);
  } catch (error) {
    return { ...result, error: redactKey(`Couldn't reach the endpoint: ${(error as Error).message}`, target.apiKey) };
  }

  result.ok = result.answers && result.tools && result.vision;
  if (!result.tools) result.error = "The model didn't call the test tool: the agent needs tool calling.";
  else if (!result.vision) result.error = "The model didn't read the test image: the agent needs image input.";
  return result;
}

function openAiToolBody(model: string) {
  return {
    model,
    messages: [{ role: "user", content: 'Call the record_answer tool with answer "ok".' }],
    tools: [{ type: "function", function: TOOL }],
    tool_choice: "auto",
  };
}

function openAiImageBody(model: string) {
  return {
    model,
    messages: [
      {
        role: "user",
        content: [
          { type: "image_url", image_url: { url: `data:image/png;base64,${RED_PNG}` } },
          { type: "text", text: "What colour is this image? Answer with one word." },
        ],
      },
    ],
  };
}

function claudeToolBody(model: string) {
  return {
    model,
    max_tokens: 1024,
    tools: [{ name: TOOL.name, description: TOOL.description, input_schema: TOOL.parameters }],
    messages: [{ role: "user", content: 'Call the record_answer tool with answer "ok".' }],
  };
}

function claudeImageBody(model: string) {
  return {
    model,
    max_tokens: 1024,
    messages: [
      {
        role: "user",
        content: [
          { type: "image", source: { type: "base64", media_type: "image/png", data: RED_PNG } },
          { type: "text", text: "What colour is this image? Answer with one word." },
        ],
      },
    ],
  };
}

type OpenAiReply = { choices?: { message?: { content?: string | null; tool_calls?: { function?: { name?: string } }[] } }[] };
type ClaudeReply = { content?: { type: string; name?: string; text?: string }[] };

function openAiCalledTool(body: unknown): boolean {
  const message = (body as OpenAiReply).choices?.[0]?.message;
  if (message?.tool_calls?.some((call) => call.function?.name === TOOL.name)) return true;
  return (message?.content ?? "").includes(`"${TOOL.name}"`); // some models write the call as JSON text
}

function openAiText(body: unknown): string {
  return (body as OpenAiReply).choices?.[0]?.message?.content ?? "";
}

function claudeCalledTool(body: unknown): boolean {
  return ((body as ClaudeReply).content ?? []).some((block) => block.type === "tool_use" && block.name === TOOL.name);
}

function claudeText(body: unknown): string {
  return ((body as ClaudeReply).content ?? []).map((block) => block.text ?? "").join(" ");
}

function errorText(body: unknown): string {
  const error = (body as { error?: { message?: string } | string })?.error;
  const message = typeof error === "string" ? error : (error?.message ?? JSON.stringify(body ?? ""));
  return message.slice(0, 200);
}

/** POST JSON to `url`, connecting to `ip` (already validated). 30 s limit, 256 KB reply cap. */
export function postJsonPinned(url: string, ip: string, headers: Record<string, string>, body: unknown): Promise<HttpReply> {
  const send = url.startsWith("https:") ? httpsRequest : httpRequest;
  const payload = JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = send(
      url,
      {
        method: "POST",
        lookup: pinnedLookup(ip) as never,
        timeout: 30_000,
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload), ...headers },
      },
      (response) => {
        let text = "";
        response.setEncoding("utf8");
        response.on("data", (chunk: string) => {
          text += chunk;
          if (text.length > 256_000) req.destroy(new Error("reply too large"));
        });
        response.on("end", () => {
          let parsed: unknown = text;
          try {
            parsed = JSON.parse(text);
          } catch {
            // not JSON: keep the text for the error message
          }
          resolve({ status: response.statusCode ?? 0, body: parsed });
        });
      },
    );
    req.on("timeout", () => req.destroy(new Error("timed out after 30 s")));
    req.on("error", reject);
    req.end(payload);
  });
}

/** Real network: resolve once, check, and pin every request to the first checked address. */
export function realProbeDeps(devMode = process.env.DEV_MODE === "true"): ProbeDeps {
  const pinned = new Map<string, string>();
  return {
    devMode,
    resolveIps: async (host) => {
      const ips = (await lookup(host, { all: true })).map((entry) => entry.address);
      if (ips[0]) pinned.set(host, ips[0]);
      return ips;
    },
    post: (url, headers, body) => {
      const ip = pinned.get(new URL(url).hostname);
      if (!ip) return Promise.reject(new Error("host was not checked"));
      return postJsonPinned(url, ip, headers, body);
    },
  };
}
