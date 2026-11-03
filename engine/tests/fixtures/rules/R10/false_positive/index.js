import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function build() {
  const server = new McpServer({ name: "calc", version: "1.0.0" });
  server.tool("add", "Add two numbers", { a: z.number(), b: z.number() }, async ({ a, b }) => ({
    content: [{ type: "text", text: String(a + b) }],
  }));
  return server;
}
