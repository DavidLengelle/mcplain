import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFileSync } from "node:fs";
import { z } from "zod";

function readNote(path) {
  return readFileSync(path, "utf8");
}

const reader = readNote;

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
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
