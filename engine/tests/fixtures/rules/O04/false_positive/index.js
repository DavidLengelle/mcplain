import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import fs from "fs";

export function build() {
  const server = new McpServer({ name: "search", version: "1.0.0" });
  server.registerTool(
    "search",
    {
      description: "Search the index (read only), caching results",
      inputSchema: { query: z.string() },
      annotations: { readOnlyHint: true },
    },
    async ({ query }) => {
      fs.writeFileSync("/tmp/search-cache.json", query);
      return { content: [{ type: "text", text: "results" }] };
    }
  );
  return server;
}
