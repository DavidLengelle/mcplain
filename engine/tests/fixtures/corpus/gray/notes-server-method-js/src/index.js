import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFileSync } from "node:fs";
import { z } from "zod";

class NoteStore {
  read(path) {
    return readFileSync(path, "utf8");
  }
}

function openStore() {
  return new NoteStore();
}

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  const store = openStore();
  server.registerTool(
    "show_note",
    { description: "Show the text of a note", inputSchema: { path: z.string() } },
    async ({ path }) => {
      const text = store.read(path);
      return { content: [{ type: "text", text }] };
    },
  );
  return server;
}
