import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "./test";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");

test("the privacy page has its four parts in English and in French, linked from the footer", async ({ page }) => {
  await page.goto("/");
  await page.locator("footer").getByRole("link", { name: "Privacy" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(["Counting the visits (Umami)", "The cookies", "Your IP address", "Your e-mail address"]);
  await page.goto("/fr/privacy");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Confidentialité");
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(["La mesure des visites (Umami)", "Les cookies", "Ton adresse IP", "Ton adresse e-mail"]);
  await expect(page.locator("[data-privacy]")).toContainText("Do Not Track");
});

for (const theme of ["light", "dark"] as const) {
  test(`screenshot of the privacy page, ${theme} theme, 390 px, without sideways scroll`, async ({ page }) => {
    mkdirSync(SCREENS, { recursive: true });
    await page.setViewportSize({ width: 390, height: 900 });
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/fr/privacy");
    await expect(page.locator("[data-privacy]")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(SCREENS, `privacy-${theme}-390.png`), fullPage: true });
  });
}
