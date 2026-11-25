import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFileSync } from "node:fs";
import { z } from "zod";

const notes = {
  read: (path) => readFileSync(path, "utf8"),
};

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  server.registerTool(
    "show_note",
    { description: "Show the text of a note", inputSchema: { path: z.string() } },
    async ({ path }) => {
      const text = notes.read(path);
      return { content: [{ type: "text", text }] };
    },
  );
  return server;
}
