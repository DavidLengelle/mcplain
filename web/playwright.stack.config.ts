import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e/stack",
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  timeout: 180_000,
  use: {
    baseURL: process.env.MCPLAIN_SITE_URL ?? "http://127.0.0.1:3000",
    locale: "en-US",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
