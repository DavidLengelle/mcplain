import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { AxiosInstance } from "axios";
import { AxiosError, type AxiosResponse } from "axios";
import { z } from "zod";

const server = new McpServer({ name: "unit-converter", version: "1.0.0" });

function label(client?: AxiosInstance, last?: AxiosResponse): string {
  return "unit converter";
}

server.registerTool(
  "to_meters",
  { description: "Convert feet to meters", inputSchema: { feet: z.number() } },
  async ({ feet }) => {
    try {
      return { content: [{ type: "text", text: String(feet * 0.3048) }] };
    } catch (error) {
      if (error instanceof AxiosError) {
        return { content: [{ type: "text", text: label() }] };
      }
      throw error;
    }
  },
);
