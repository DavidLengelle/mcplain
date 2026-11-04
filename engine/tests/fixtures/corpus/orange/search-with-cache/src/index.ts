import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { z } from "zod";

const WORDS = ["apple", "apricot", "banana", "blueberry", "cherry"];
const CACHE = ".search-cache.json";

function search(prefix: string): string[] {
  let cache: Record<string, string[]> = {};
  if (existsSync(CACHE)) {
    cache = JSON.parse(readFileSync(CACHE, "utf8"));
  }
  if (!cache[prefix]) {
    cache[prefix] = WORDS.filter((word) => word.startsWith(prefix));
    writeFileSync(CACHE, JSON.stringify(cache));
  }
  return cache[prefix];
}

export function build(): McpServer {
  const server = new McpServer({ name: "search-cache", version: "1.0.0" });
  server.registerTool(
    "search_words",
    {
      description: "Find the fruit names that start with a prefix",
      inputSchema: { prefix: z.string() },
      annotations: { readOnlyHint: true },
    },
    async ({ prefix }) => ({ content: [{ type: "text", text: search(prefix).join(", ") }] }),
  );
  return server;
}
