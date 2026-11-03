import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function build() {
  const server = new McpServer({ name: "browser", version: "1.0.0" });
  server.tool("open", "Open a page", { url: z.string() }, async ({ url }) => ({
    content: [{ type: "text", text: url }],
  }));
  return server;
}
