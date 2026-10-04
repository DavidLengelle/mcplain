import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { readFile } from "node:fs/promises";
import { z } from "zod";
import { deleteHandler } from "./handlers.js";

const server = new McpServer({ name: "files", version: "1.0.0" });

const readHandler = async (args: { path: string }) => {
  const text = await readFile(args.path, "utf8");
  return { content: [{ type: "text" as const, text }] };
};

server.registerTool("read", { description: "Read a file", inputSchema: { path: z.string() } }, readHandler);
server.registerTool("delete", { description: "Delete a file", inputSchema: { path: z.string() } }, deleteHandler);
