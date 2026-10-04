import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import fs from "fs";

export function build() {
  const server = new McpServer({ name: "fsys", version: "1.0.0" });
  server.registerTool(
    "create_directory",
    {
      description: "Create a directory",
      inputSchema: { path: z.string() },
      annotations: { destructiveHint: false },
    },
    async ({ path }) => {
      fs.mkdirSync(path, { recursive: true });
      return { content: [{ type: "text", text: "created" }] };
    }
  );
  return server;
}
