import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFileSync } from "node:fs";
import { z } from "zod";

function makeReader() {
  return (path) => readFileSync(path, "utf8");
}

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  const reader = makeReader();
  server.registerTool(
    "show_note",
    { description: "Show the text of a note", inputSchema: { path: z.string() } },
    async ({ path }) => {
      const text = reader(path);
      return { content: [{ type: "text", text }] };
    },
  );
  return server;
}
