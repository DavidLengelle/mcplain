import fs from "fs";
import os from "os";
import path from "path";

export function saveSettings() {
  const target = path.join(os.homedir(), ".notes-mcp", "settings.json");
  fs.writeFileSync(target, JSON.stringify({ folder: "notes" }, null, 2));
}
