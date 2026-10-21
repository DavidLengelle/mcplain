import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const WEB_PORT_VARIABLE = "MCPLAIN_WEB_PORT";
const DEFAULT_WEB_PORT = "3000";

function webPort(): string {
  const fromEnvironment = process.env[WEB_PORT_VARIABLE];
  if (fromEnvironment) {
    return fromEnvironment;
  }
  const envFile = join(__dirname, "..", ".env");
  if (existsSync(envFile)) {
    for (const line of readFileSync(envFile, "utf-8").split("\n")) {
      const [name, ...rest] = line.split("=");
      const value = rest.join("=").trim();
      if (name.trim() === WEB_PORT_VARIABLE && value !== "") {
        return value;
      }
    }
  }
  return DEFAULT_WEB_PORT;
}

export default defineConfig({
  testDir: "tests/e2e/stack",
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  timeout: 180_000,
  use: {
    baseURL: process.env.MCPLAIN_SITE_URL ?? `http://127.0.0.1:${webPort()}`,
    locale: "en-US",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
