import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const server = new McpServer({ name: "a", version: "1.0.0" });
server.tool("hello", "Say hello", async () => ({ content: [{ type: "text", text: "hello" }] }));
