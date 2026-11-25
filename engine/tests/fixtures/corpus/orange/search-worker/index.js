import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Worker } from "node:worker_threads";
import { z } from "zod";

export function build() {
  const server = new McpServer({ name: "notes-search", version: "1.0.0" });
  server.registerTool(
    "search_notes",
    { description: "Search the notes in a background worker", inputSchema: { query: z.string() } },
    async ({ query }) => {
      const worker = new Worker(new URL("./search.js", import.meta.url), { workerData: { query } });
      worker.terminate();
      return { content: [{ type: "text", text: query }] };
    },
  );
  return server;
}
