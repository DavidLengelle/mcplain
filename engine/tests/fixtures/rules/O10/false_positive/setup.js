import fs from "fs";
import os from "os";
import path from "path";

export function setupCursor(options) {
  const target = path.join(os.homedir(), ".cursor/mcp.json");
  const body = JSON.stringify({ mcpServers: { notes: { command: "npx", args: ["-y", "notes-mcp"] } } }, null, 2);
  if (!options.write) {
    return `Dry run, pass --write to write ${target}:\n${body}`;
  }
  fs.writeFileSync(target, body);
  return `Wrote ${target}`;
}
