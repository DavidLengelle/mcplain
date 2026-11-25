import type { Page } from "@playwright/test";

import { expect, test } from "./test";

import { fulfill, ID, serveAnalysis } from "./fake-api";
import { reportView } from "./reports";

const NARROW = [320, 390] as const;
const REFUSED = { error: { code: "input.unrecognized", params: {} } };

async function sideways(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

for (const width of NARROW) {
  test(`the home page with a refused input has no sideways scroll, ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.route("**/api/analyses", async (route) => {
      await fulfill(route, 400, REFUSED);
    });
    await page.goto("/fr");
    await page.locator("#home-input").fill("hello");
    await page.locator("#analyser button[type=submit]").click();
    await expect(page.locator("#home-error")).not.toBeEmpty();
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });

  for (const name of ["orange", "red", "failed", "multiple"] as const) {
    test(`the ${name} report has no sideways scroll, ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await serveAnalysis(page, [reportView(name)]);
      await page.goto(`/fr/analyses/${ID}`);
      await expect(page.locator("[data-report]")).toBeVisible();
      expect(await sideways(page)).toBeLessThanOrEqual(0);
    });
  }
}

for (const path of ["/fr", `/fr/analyses/${ID}`]) {
  for (const width of [390, 1280] as const) {
    test(`the round arrow is absent at the top and comes after one screen, ${path}, ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await serveAnalysis(page, [reportView("orange")]);
      await page.goto(path);
      await expect(page.locator("#home-input, [data-verdict]").first()).toBeVisible();
      await expect(page.locator("[data-back-to-top]")).toHaveCount(0);
      await page.evaluate(() => window.scrollTo({ top: window.innerHeight - 50, behavior: "instant" }));
      await expect(page.locator("[data-back-to-top]")).toHaveCount(0);
      await page.evaluate(() => window.scrollTo({ top: window.innerHeight + 10, behavior: "instant" }));
      await expect(page.locator("[data-back-to-top]")).toBeVisible();
      await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
      const arrow = await page.locator("[data-back-to-top]").boundingBox();
      const lastText = await page.locator("footer").evaluate((footer) => {
        let bottom = 0;
        for (const item of footer.querySelectorAll("a, span")) {
          bottom = Math.max(bottom, item.getBoundingClientRect().bottom);
        }
        return bottom;
      });
      expect(arrow).not.toBeNull();
      expect(lastText).toBeLessThanOrEqual(arrow?.y ?? 0);
    });
  }
}

test("on a wide screen, the round arrow stays in the right margin, beside the text", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/fr/analyses/${ID}`);
  await expect(page.locator("[data-verdict]")).toBeVisible();
  await page.evaluate(() => window.scrollTo({ top: window.innerHeight * 2, behavior: "instant" }));
  const arrow = await page.locator("[data-back-to-top]").boundingBox();
  const content = await page.locator("[data-report]").boundingBox();
  expect(arrow?.x ?? 0).toBeGreaterThanOrEqual((content?.x ?? 0) + (content?.width ?? 0));
});
