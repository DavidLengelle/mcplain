import { copyFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const source = join(process.cwd(), "node_modules", "altcha", "dist", "workers", "pbkdf2.js");
const folder = join(process.cwd(), "public", "altcha");

mkdirSync(folder, { recursive: true });
copyFileSync(source, join(folder, "pbkdf2.js"));
