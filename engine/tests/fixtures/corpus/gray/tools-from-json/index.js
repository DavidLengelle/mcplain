import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFileSync } from "node:fs";
import { z } from "zod";

export function build() {
  const units = JSON.parse(readFileSync(new URL("./units.json", import.meta.url), "utf8"));
  const server = new McpServer({ name: "unit-table", version: "1.0.0" });
  for (const unit of units) {
    server.registerTool(unit.name, { description: unit.description, inputSchema: { value: z.number() } }, async ({ value }) => ({
      content: [{ type: "text", text: String(value * unit.factor) }],
    }));
  }
  return server;
}
