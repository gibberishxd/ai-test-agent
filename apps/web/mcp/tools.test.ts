import { describe, expect, it } from "vitest";
import { createServer, PROTOCOL_VERSIONS, TOOLS } from "./tools";

type Call = { url: string; init: RequestInit };

function fakeApi(responses: Array<{ status: number; body: unknown; type?: string }>) {
  const calls: Call[] = [];
  const fetchFn = async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const next = responses.shift() ?? { status: 500, body: { error: "no more answers" } };
    const text = typeof next.body === "string" ? next.body : JSON.stringify(next.body);
    return new Response(text, { status: next.status, headers: { "content-type": next.type ?? "application/json" } });
  };
  return { calls, fetchFn };
}

const config = { baseUrl: "https://ata.test/", apiKey: "ata_secret" };

describe("MCP server (run 7, M5)", () => {
  it("answers initialize with a protocol version both sides support and its tools capability", async () => {
    const server = createServer(config, fakeApi([]).fetchFn);
    const reply = await server.handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: PROTOCOL_VERSIONS[1] } });
    expect(reply).toMatchObject({ jsonrpc: "2.0", id: 1, result: { protocolVersion: PROTOCOL_VERSIONS[1], capabilities: { tools: {} }, serverInfo: { name: "ai-test-agent" } } });
    const unknown = await server.handle({ jsonrpc: "2.0", id: 2, method: "initialize", params: { protocolVersion: "1999-01-01" } });
    expect((unknown as { result: { protocolVersion: string } }).result.protocolVersion).toBe(PROTOCOL_VERSIONS[0]);
  });

  it("lists exactly the three tools the API backs, with input schemas", async () => {
    const server = createServer(config, fakeApi([]).fetchFn);
    const reply = (await server.handle({ jsonrpc: "2.0", id: 1, method: "tools/list" })) as { result: { tools: { name: string; inputSchema: object }[] } };
    expect(reply.result.tools.map((t) => t.name)).toEqual(["start_run", "get_run_status", "get_report"]);
    expect(TOOLS.every((t) => t.inputSchema && (t.inputSchema as { type: string }).type === "object")).toBe(true);
  });

  it("starts a run through /api/v1 with the workspace key, never echoing the key", async () => {
    const api = fakeApi([{ status: 201, body: { id: "r1", status: "queued", finished: false } }]);
    const server = createServer(config, api.fetchFn);
    const reply = (await server.handle({
      jsonrpc: "2.0",
      id: 7,
      method: "tools/call",
      params: { name: "start_run", arguments: { target_url: "https://staging.example.com", mode: "interactive", max_steps: 20 } },
    })) as { result: { content: { type: string; text: string }[]; isError?: boolean } };
    expect(api.calls[0].url).toBe("https://ata.test/api/v1/runs");
    expect(api.calls[0].init.method).toBe("POST");
    expect((api.calls[0].init.headers as Record<string, string>).authorization).toBe("Bearer ata_secret");
    expect(JSON.parse(String(api.calls[0].init.body))).toEqual({ target_url: "https://staging.example.com", mode: "interactive", max_steps: 20 });
    expect(reply.result.isError).toBeFalsy();
    expect(reply.result.content[0].text).toContain('"id": "r1"');
    expect(JSON.stringify(reply)).not.toContain("ata_secret");
  });

  it("reads a run's status and its report, JSON or JUnit", async () => {
    const api = fakeApi([
      { status: 200, body: { id: "r1", status: "done", finished: true } },
      { status: 200, body: "<testsuites/>", type: "application/xml" },
    ]);
    const server = createServer(config, api.fetchFn);
    await server.handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_run_status", arguments: { run_id: "r1" } } });
    const report = (await server.handle({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_report", arguments: { run_id: "r1", format: "junit" } } })) as {
      result: { content: { text: string }[] };
    };
    expect(api.calls.map((c) => c.url)).toEqual(["https://ata.test/api/v1/runs/r1", "https://ata.test/api/v1/runs/r1/report?format=junit"]);
    expect(report.result.content[0].text).toBe("<testsuites/>");
  });

  it("returns an API refusal as a tool error the model can read, not a protocol error", async () => {
    const api = fakeApi([{ status: 400, body: { errors: { mode: "Verify the domain first." } } }]);
    const server = createServer(config, api.fetchFn);
    const reply = (await server.handle({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "start_run", arguments: { target_url: "https://x.test", mode: "interactive" } } })) as {
      result: { isError: boolean; content: { text: string }[] };
    };
    expect(reply.result.isError).toBe(true);
    expect(reply.result.content[0].text).toContain("400");
    expect(reply.result.content[0].text).toContain("Verify the domain first.");
  });

  it("refuses unknown tools, bad arguments and unknown methods; ignores notifications", async () => {
    const server = createServer(config, fakeApi([]).fetchFn);
    const unknownTool = (await server.handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "delete_everything", arguments: {} } })) as { error: { code: number } };
    expect(unknownTool.error.code).toBe(-32602);
    const badArgs = (await server.handle({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_report", arguments: { run_id: "../../admin" } } })) as { error: { code: number } };
    expect(badArgs.error.code).toBe(-32602);
    const unknownMethod = (await server.handle({ jsonrpc: "2.0", id: 3, method: "resources/list" })) as { error: { code: number } };
    expect(unknownMethod.error.code).toBe(-32601);
    expect(await server.handle({ jsonrpc: "2.0", method: "notifications/initialized" })).toBeNull();
  });
});
