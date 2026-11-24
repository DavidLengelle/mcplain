import { defineConfig, devices } from "@playwright/test";

const SITE_PORT = 3100;
const MESSAGES_PORT = 3101;
const UMAMI_PORT = 3102;
export const UMAMI_RECORDS = `http://127.0.0.1:${UMAMI_PORT}/records`;
export const TEST_WEBSITE_ID = "b59e9c65-ae32-47f1-8400-119fcf4861c4";


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
      command: `node tests/e2e/umami-server.mjs ${UMAMI_PORT}`,
      url: `http://127.0.0.1:${UMAMI_PORT}/health`,
      reuseExistingServer: false,
    },
    {
      command: `pnpm exec next start --hostname localhost --port ${SITE_PORT}`,
      url: `http://127.0.0.1:${SITE_PORT}`,
      reuseExistingServer: false,
      env: {
        MCPLAIN_API_URL: `http://127.0.0.1:${MESSAGES_PORT}`,
        MCPLAIN_UMAMI_URL: `http://127.0.0.1:${UMAMI_PORT}`,
        MCPLAIN_UMAMI_WEBSITE_ID: TEST_WEBSITE_ID,
        NODE_OPTIONS: "--dns-result-order=ipv4first --require ./client-ip.js",
      },
    },
  ],
});
