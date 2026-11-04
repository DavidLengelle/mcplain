import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function build(): McpServer {
  const server = new McpServer({ name: "calculator", version: "1.0.0" });

  server.registerTool(
    "add",
    {
      title: "Add",
      description: "Add two numbers",
      inputSchema: { a: z.number(), b: z.number() },
    },
    async ({ a, b }) => ({ content: [{ type: "text", text: String(a + b) }] }),
  );

  server.registerTool(
    "multiply",
    {
      title: "Multiply",
      description: "Multiply two numbers",
      inputSchema: { a: z.number(), b: z.number() },
    },
    async ({ a, b }) => ({ content: [{ type: "text", text: String(a * b) }] }),
  );

  return server;
}
