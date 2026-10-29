import { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";

const server = new McpServer({ name: "clock", version: "1.0.0" });

server.registerTool(
  "now",
  { description: "Tell the time", inputSchema: { zone: z.string() } },
  async ({ zone }) => ({ content: [{ type: "text", text: new Date().toLocaleString("en", { timeZone: zone }) }] }),
);
