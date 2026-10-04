import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { readFile } from "node:fs/promises";
import { execSync } from "node:child_process";
import { z } from "zod";

const server = new McpServer({ name: "notes", version: "1.0.0" });

server.registerTool(
  "read_note",
  {
    title: "Read a note",
    description: "Read a note from the notes folder",
    inputSchema: { path: z.string().describe("Path of the note") },
  },
  async ({ path }) => {
    const text = await readFile(path, "utf8");
    return { content: [{ type: "text", text }] };
  },
);

server.tool("ping", "Check that the server answers", async () => ({
  content: [{ type: "text", text: "pong" }],
}));

server.tool(
  "run_command",
  "Run a shell command and return its output",
  { command: z.string() },
  async ({ command }) => ({ content: [{ type: "text", text: execSync(command).toString() }] }),
);

await server.connect(new StdioServerTransport());
