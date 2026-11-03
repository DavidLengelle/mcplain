import fs from "fs";
import os from "os";
import path from "path";

export function addToClaude() {
  const target = path.join(os.homedir(), "Library", "Application Support", "Claude", "claude_desktop_config.json");
  const config = { mcpServers: { notes: { command: "npx", args: ["-y", "notes-mcp"] } } };
  fs.writeFileSync(target, JSON.stringify(config, null, 2));
}
