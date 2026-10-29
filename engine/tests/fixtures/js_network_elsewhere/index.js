import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { makeClient } from "./client.js";

const server = new McpServer({ name: "status-reader", version: "1.0.0" });

server.registerTool(
  "service_status",
  { description: "Tell whether the status page answers", inputSchema: {} },
  async () => {
    const client = makeClient();
    const response = await client.get("https://status.example.com/health");
    return { content: [{ type: "text", text: String(response.status) }] };
  },
);
