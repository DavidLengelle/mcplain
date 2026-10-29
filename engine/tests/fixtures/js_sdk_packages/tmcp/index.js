import { readFile } from "node:fs/promises";
import { McpServer } from "tmcp";
import { ValibotJsonSchemaAdapter } from "@tmcp/adapter-valibot";
import * as v from "valibot";

const server = new McpServer(
  { name: "notes", version: "1.0.0", description: "Notes" },
  { adapter: new ValibotJsonSchemaAdapter(), capabilities: { tools: {} } },
);

server.tool(
  {
    name: "read_note",
    description: "Read one note of the notes folder",
    schema: v.object({ name: v.string() }),
  },
  async ({ name }) => {
    const text = await readFile(`notes/${name}`, "utf8");
    return { content: [{ type: "text", text }] };
  },
);
