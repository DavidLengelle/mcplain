import { defineConfig, devices } from "@playwright/test";

const SITE_PORT = 3100;
const MESSAGES_PORT = 3101;

export default defineConfig({
  testDir: "tests/e2e",
  testIgnore: ["stack/**"],
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${SITE_PORT}`,
    locale: "en-US",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `node tests/e2e/messages-server.mjs ${MESSAGES_PORT}`,
      url: `http://127.0.0.1:${MESSAGES_PORT}/health`,
      reuseExistingServer: false,
    },
    {
      command: `pnpm exec next start --hostname localhost --port ${SITE_PORT}`,
      url: `http://127.0.0.1:${SITE_PORT}`,
      reuseExistingServer: false,
      env: { MCPLAIN_API_URL: `http://127.0.0.1:${MESSAGES_PORT}`, NODE_OPTIONS: "--dns-result-order=ipv4first" },
    },
  ],
});
