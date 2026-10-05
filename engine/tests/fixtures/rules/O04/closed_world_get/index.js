import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

export function build() {
  const server = new McpServer({ name: "status", version: "1.0.0" });
  server.registerTool(
    "status",
    {
      description: "Read the service status",
      inputSchema: {},
      annotations: { openWorldHint: false },
    },
    async () => {
      const response = await fetch("https://example.com/status");
      return { content: [{ type: "text", text: await response.text() }] };
    }
  );
  return server;
}
