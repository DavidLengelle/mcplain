import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import fs from "node:fs";
import { z } from "zod";

const O_RDONLY = fs.constants.O_WRONLY;

function logFlags() {
  return fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_APPEND;
}

function openWith(path, flags) {
  return fs.openSync(path, flags);
}

function openOrRead(path, flags) {
  return fs.openSync(path, flags ?? 0);
}


export function build() {
  const server = new McpServer({ name: "lookups", version: "1.0.0" });
  server.registerTool(
    "log_lookup",
    { description: "Look up a note and log the lookup", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync("lookups.log", logFlags());
      fs.closeSync(fd);
      return { content: [{ type: "text", text: path }] };
    },
  );
  server.registerTool(
    "check_note",
    { description: "Check that a note can be opened", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, fs.constants.O_RDWR);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "peek_note",
    { description: "Peek at a note", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, O_RDONLY);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "raw_note",
    { description: "Open a note by number flags", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, 0);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "given_note",
    { description: "Open a note with given flags", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = openWith(path, fs.constants.O_RDONLY);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "args_note",
    { description: "Open a note with the flags of the request", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async (args) => {
      const fd = fs.openSync(args.path, args.flags ?? 0);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "fallback_note",
    { description: "Open a note with given flags or the default", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = openOrRead(path, fs.constants.O_RDONLY);
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  server.registerTool(
    "mixed_note",
    { description: "Open a note without following links", inputSchema: { path: z.string() }, annotations: { readOnlyHint: true } },
    async ({ path }) => {
      const fd = fs.openSync(path, fs.constants.O_WRONLY | (fs.constants.O_NOFOLLOW ?? 0));
      fs.closeSync(fd);
      return { content: [{ type: "text", text: "ok" }] };
    },
  );
  return server;
}
