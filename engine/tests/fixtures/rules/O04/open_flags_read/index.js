import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import fs from "node:fs";
import { z } from "zod";

const { O_RDONLY, O_NOFOLLOW } = fs.constants;

function noFollow() {
  return fs.constants.O_NOFOLLOW ?? 0;
}

function readFlags() {
  return fs.constants.O_RDONLY | noFollow() | (fs.constants.O_NONBLOCK ?? 0);
}

export function build() {
  const server = new McpServer({ name: "notes", version: "1.0.0" });
  server.registerTool(
    "read_note",
    { description: "Read a note", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, readFlags());
      const text = fs.readFileSync(fd, "utf8");
      fs.closeSync(fd);
      return { content: [{ type: "text", text }] };
    },
  );
  server.registerTool(
    "read_head",
    { description: "Read the start of a note", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, O_RDONLY | O_NOFOLLOW);
      const text = fs.readFileSync(fd, "utf8").slice(0, 200);
      fs.closeSync(fd);
      return { content: [{ type: "text", text }] };
    },
  );
  return server;
}
