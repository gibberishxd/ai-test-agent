/**
 * The AI Test Agent MCP server over stdio (run 7, M5). Run with Node 24 or later:
 *
 *   ATA_URL=https://your-ata.example.com ATA_API_KEY=ata_... node apps/web/mcp/server.ts
 *
 * Reads one JSON-RPC message per line from stdin and writes each reply as one line to stdout.
 * Logs go to stderr only (stdout is the protocol). The API key comes from the environment and is
 * never written anywhere. Setup for Claude Code and Cursor: README, "Use it from your editor".
 */
import { createInterface } from "node:readline";
import { createServer, type Message } from "./tools.ts";

const baseUrl = process.env.ATA_URL;
const apiKey = process.env.ATA_API_KEY;
if (!baseUrl || !apiKey) {
  process.stderr.write("Set ATA_URL (your AI Test Agent address) and ATA_API_KEY (Settings → API keys).\n");
  process.exit(1);
}

const server = createServer({ baseUrl, apiKey });
const lines = createInterface({ input: process.stdin });

lines.on("line", async (line) => {
  if (!line.trim()) return;
  let message: Message;
  try {
    message = JSON.parse(line) as Message;
  } catch {
    process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }) + "\n");
    return;
  }
  const reply = await server.handle(message);
  if (reply) process.stdout.write(JSON.stringify(reply) + "\n");
});
