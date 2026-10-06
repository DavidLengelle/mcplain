import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { ID, serveAnalysis } from "./fake-api";
import { reportView, type ReportName } from "./reports";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");
const VERDICTS: ReportName[] = ["green", "orange", "red"];
const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;

for (const verdict of VERDICTS) {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      test(`screenshot of the ${verdict} report, ${theme} theme, ${width} px`, async ({ page }) => {
        mkdirSync(SCREENS, { recursive: true });
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: theme });
        await serveAnalysis(page, [reportView(verdict)]);
        await page.goto(`/fr/analyses/${ID}`);
        await expect(page.locator("[data-verdict]")).toBeVisible();
        await page.screenshot({ path: join(SCREENS, `${verdict}-${theme}-${width}.png`), fullPage: true });
      });
    }
  }
}
