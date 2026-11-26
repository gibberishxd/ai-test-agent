/**
 * The MCP server's logic (run 7, M5; roadmap item 6): start a run, get its status, get its report,
 * from Claude Code, Cursor or any MCP client. Only what /api/v1 already does, with a workspace
 * API key: the API's own rules apply (quota, verified domains, rate limits).
 *
 * No SDK: MCP over stdio is JSON-RPC 2.0, one message per line, and this server needs three
 * methods (initialize, tools/list, tools/call). Fewer dependencies, nothing to keep patched.
 * `server.ts` connects it to stdin/stdout.
 */

export const PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];
const RUN_ID = /^[A-Za-z0-9-]{1,64}$/;

type Json = Record<string, unknown>;
export type Message = { jsonrpc: "2.0"; id?: string | number | null; method?: string; params?: Json };
type Fetch = (url: string, init?: RequestInit) => Promise<Response>;
export type Config = { baseUrl: string; apiKey: string };

export const TOOLS = [
  {
    name: "start_run",
    title: "Start a test run",
    description:
      "Start an AI test run on a web app: the agent explores it like a manual QA tester and reports bugs with evidence. " +
      "Returns the run's id and status; poll get_run_status until finished is true, then get_report. " +
      "Interactive and deep mode need a domain verified in the workspace (or the demo shop). " +
      "Deep mode maps the app, plans its tests and checks three screen sizes with a strong model: thorough, slower and costlier.",
    inputSchema: {
      type: "object",
      required: ["target_url"],
      additionalProperties: false,
      properties: {
        target_url: { type: "string", description: "The URL to test, e.g. https://staging.example.com" },
        mode: {
          type: "string",
          enum: ["passive", "interactive", "deep"],
          description: "passive (default) only looks; interactive clicks, types and submits; deep is deep mode.",
        },
        engine_model: { type: "string", enum: ["claude-sonnet-5-5", "claude-opus-5-5"], description: "Deep mode's model (default Sonnet 5.5)." },
        focus: { type: "string", description: 'What to concentrate on, e.g. "checkout".' },
        max_steps: { type: "integer", minimum: 1, maximum: 100 },
        max_minutes: { type: "integer", minimum: 1, maximum: 60 },
      },
    },
  },
  {
    name: "get_run_status",
    title: "Get a run's status",
    description: "A run's status: queued, running, done, failed, stopped or paused (deep mode, a usage limit), with counts of findings so far.",
    inputSchema: { type: "object", required: ["run_id"], additionalProperties: false, properties: { run_id: { type: "string" } } },
  },
  {
    name: "get_report",
    title: "Get a run's report",
    description: "A finished run's findings: each with severity, steps to reproduce, expected and actual. JSON by default, or JUnit XML.",
    inputSchema: {
      type: "object",
      required: ["run_id"],
      additionalProperties: false,
      properties: { run_id: { type: "string" }, format: { type: "string", enum: ["json", "junit"] } },
    },
  },
] as const;

class InvalidParams extends Error {}

export function createServer(config: Config, fetchFn: Fetch = fetch) {
  const base = config.baseUrl.replace(/\/+$/, "");

  async function api(path: string, init: RequestInit = {}) {
    const response = await fetchFn(`${base}${path}`, {
      ...init,
      headers: { authorization: `Bearer ${config.apiKey}`, "content-type": "application/json", ...(init.headers as Record<string, string> | undefined) },
    });
    const text = await response.text();
    let shown = text;
    try {
      shown = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      // not JSON (a JUnit report): shown as it is
    }
    if (!response.ok) return { content: [{ type: "text", text: `The API answered ${response.status}: ${shown}` }], isError: true };
    return { content: [{ type: "text", text: shown }] };
  }

  function runId(args: Json): string {
    const id = args.run_id;
    if (typeof id !== "string" || !RUN_ID.test(id)) throw new InvalidParams("run_id must be a run's id.");
    return id;
  }

  async function callTool(name: unknown, args: Json) {
    if (name === "start_run") {
      if (typeof args.target_url !== "string" || !args.target_url) throw new InvalidParams("target_url is required.");
      const allowed = ["target_url", "mode", "engine_model", "focus", "max_steps", "max_minutes"];
      const body = Object.fromEntries(Object.entries(args).filter(([key]) => allowed.includes(key)));
      return api("/api/v1/runs", { method: "POST", body: JSON.stringify(body) });
    }
    if (name === "get_run_status") return api(`/api/v1/runs/${runId(args)}`);
    if (name === "get_report") {
      const format = args.format === "junit" ? "?format=junit" : "";
      return api(`/api/v1/runs/${runId(args)}/report${format}`);
    }
    throw new InvalidParams(`Unknown tool: ${String(name)}`);
  }

  async function handle(message: Message): Promise<Json | null> {
    if (message.id === undefined || message.id === null) return null; // a notification: no reply
    const reply = (body: Json) => ({ jsonrpc: "2.0", id: message.id, ...body });
    try {
      switch (message.method) {
        case "initialize": {
          const asked = String(message.params?.protocolVersion ?? "");
          return reply({
            result: {
              protocolVersion: PROTOCOL_VERSIONS.includes(asked) ? asked : PROTOCOL_VERSIONS[0],
              capabilities: { tools: {} },
              serverInfo: { name: "ai-test-agent", title: "AI Test Agent", version: "1.0.0" },
              instructions: "Start a run with start_run, poll get_run_status until finished, then read get_report.",
            },
          });
        }
        case "ping":
          return reply({ result: {} });
        case "tools/list":
          return reply({ result: { tools: TOOLS } });
        case "tools/call":
          return reply({ result: await callTool(message.params?.name, (message.params?.arguments as Json) ?? {}) });
        default:
          return reply({ error: { code: -32601, message: `Method not found: ${message.method}` } });
      }
    } catch (error) {
      if (error instanceof InvalidParams) return reply({ error: { code: -32602, message: error.message } });
      return reply({ error: { code: -32603, message: error instanceof Error ? error.message : String(error) } });
    }
  }

  return { handle };
}
