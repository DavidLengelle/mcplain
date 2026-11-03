import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  server.registerTool("count_notes", { description: "Count the notes" }, async () => {
    return { content: [{ type: "text", text: "0" }] };
  });
  return server;
}
