import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFile, writeFile, unlink } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

function inside(root, name) {
  const target = path.resolve(root, name);
  if (!target.startsWith(path.resolve(root) + path.sep)) {
    throw new Error("Outside the notes folder");
  }
  return target;
}

export function build() {
  const root = process.env.NOTES_DIR || "./notes";
  const server = new McpServer({ name: "notes-folder", version: "1.0.0" });

  server.registerTool(
    "read_note",
    { description: "Read a note from the notes folder", inputSchema: { name: z.string() } },
    async ({ name }) => ({ content: [{ type: "text", text: await readFile(inside(root, name), "utf8") }] }),
  );

  server.registerTool(
    "save_note",
    { description: "Write a note in the notes folder", inputSchema: { name: z.string(), text: z.string() } },
    async ({ name, text }) => {
      await writeFile(inside(root, name), text, "utf8");
      return { content: [{ type: "text", text: "saved" }] };
    },
  );

  server.registerTool(
    "delete_note",
    { description: "Delete a note from the notes folder", inputSchema: { name: z.string() } },
    async ({ name }) => {
      await unlink(inside(root, name));
      return { content: [{ type: "text", text: "deleted" }] };
    },
  );

  return server;
}
