import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { saveNote } from "./lib.js";

const server = new McpServer({ name: "notes", version: "1.0.0" });

server.registerTool(
  "save_note",
  { description: "Save a note", inputSchema: { text: z.string() } },
  async ({ text }) => {
    await saveNote(text);
    return { content: [{ type: "text", text: "saved" }] };
  },
);
