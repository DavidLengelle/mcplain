import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

type Handler = (args: { text: string }) => Promise<{ content: { type: "text"; text: string }[] }>;

interface Entry {
  description: string;
  run: Handler;
}

export class ToolBox {
  private readonly tools: Record<string, Entry> = {
    slugify: {
      description: "Turn a title into a lowercase slug with dashes",
      run: async ({ text }) => ({
        content: [{ type: "text", text: text.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") }],
      }),
    },
    reverse: {
      description: "Write a text backwards",
      run: async ({ text }) => ({ content: [{ type: "text", text: [...text].reverse().join("") }] }),
    },
  };

  register(server: McpServer): void {
    for (const [name, entry] of Object.entries(this.tools)) {
      server.registerTool(name, { description: entry.description, inputSchema: { text: z.string() } }, entry.run);
    }
  }
}
