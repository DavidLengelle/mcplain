import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ToolBox } from "./toolbox.js";

export function build(): McpServer {
  const server = new McpServer({ name: "slug-tools", version: "1.0.0" });
  new ToolBox().register(server);
  return server;
}
