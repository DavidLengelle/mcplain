import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import pg from "pg";
import { z } from "zod";

export function build(databaseUrl) {
  const pool = new pg.Pool({ connectionString: databaseUrl });
  const server = new McpServer({ name: "notes-db", version: "1.0.0" });
  server.registerTool(
    "count_notes",
    { description: "Count the notes in the database", inputSchema: { folder: z.string() } },
    async ({ folder }) => {
      const answer = await pool.query("SELECT count(*) FROM notes WHERE folder = $1", [folder]);
      return { content: [{ type: "text", text: String(answer.rows[0].count) }] };
    },
  );
  return server;
}
