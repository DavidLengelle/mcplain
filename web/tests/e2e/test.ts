import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test as base } from "@playwright/test";

const CHALLENGE = readFileSync(join(__dirname, "..", "fixtures", "altcha-challenge.json"), "utf-8");
const NOT_FOUND = JSON.stringify({ error: { code: "api.not_found", params: {} } });

export const test = base.extend<{ simulatedVisitor: void }>({
  simulatedVisitor: [
    async ({ page }, use) => {
      await page.route("**/api/altcha/challenge", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: CHALLENGE });
      });
      await page.route("**/api/quota", async (route) => {
        await route.fulfill({ status: 404, contentType: "application/json", body: NOT_FOUND });
      });
      await use();
    },
    { auto: true },
  ],
});

export { expect };
