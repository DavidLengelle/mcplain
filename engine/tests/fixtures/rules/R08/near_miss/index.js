import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import fs from "fs";

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  server.tool("save", "Save a note to a file", { path: z.string(), text: z.string() }, async ({ path, text }) => {
    fs.writeFileSync(path, text);
    return { content: [{ type: "text", text: "saved" }] };
  });
  return server;
}
