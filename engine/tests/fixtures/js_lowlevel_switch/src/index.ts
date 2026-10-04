import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { appendFileSync, readFileSync, rmSync } from "node:fs";
import { execSync } from "node:child_process";

enum ToolName {
  READ = "read_log",
  CLEAR = "clear_log",
}

const EXTRA = { STATUS: "status", RESTART: "restart" } as const;

const server = new Server({ name: "logs", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: ToolName.READ, description: "Read the log", inputSchema: { type: "object", properties: {} } },
    { name: ToolName.CLEAR, description: "Clear the log", inputSchema: { type: "object", properties: {} } },
    { name: EXTRA.STATUS, description: "Show the status", inputSchema: { type: "object", properties: {} } },
    { name: EXTRA.RESTART, description: "Restart the service", inputSchema: { type: "object", properties: {} } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  appendFileSync("audit.log", request.params.name);
  switch (request.params.name) {
    case ToolName.READ:
      return { content: [{ type: "text", text: readFileSync("app.log", "utf8") }] };
    case ToolName.CLEAR: {
      rmSync("app.log");
      return { content: [] };
    }
    case EXTRA.STATUS:
    case EXTRA.RESTART:
      execSync("systemctl status app");
      return { content: [] };
    default:
      throw new Error("Unknown tool");
  }
});
