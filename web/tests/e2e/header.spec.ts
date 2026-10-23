import { expect, test, type Locator } from "@playwright/test";

import { ID, serveAnalysis } from "./fake-api";
import { reportView } from "./reports";

const WIDTHS = [390, 1280] as const;
const LANGUAGES = [
  { prefix: "", idle: "ANALYZE", busy: "SENDING…" },
  { prefix: "/fr", idle: "ANALYSER", busy: "ENVOI…" },
] as const;

async function boxes(items: Locator): Promise<string> {
  const all = await items.evaluateAll((elements) =>
    elements.map((element) => {
      const box = element.getBoundingClientRect();
      return [box.x, box.y, box.width, box.height].map((value) => Math.round(value)).join(",");
    }),
  );
  return all.join(" ");
}

for (const width of WIDTHS) {
  for (const language of LANGUAGES) {
    test(`the header submit button shows its whole text while sending, ${language.idle}, ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await serveAnalysis(page, [reportView("green")]);
      await page.route("**/api/analyses", () => new Promise(() => {}));
      await page.goto(`${language.prefix}/analyses/${ID}`);
      await expect(page.locator("[data-verdict]")).toBeVisible();

      const header = page.locator("#site-header");
      const button = header.locator("button[type=submit]");
      const parts = header.locator("a, input, button");
      await expect(button).toHaveAccessibleName(language.idle);
      const before = await boxes(parts);

      await header.locator("input").fill("uvx mcp-server-fetch");
      await button.click();
      await expect(button).toBeDisabled();
      await expect(button).toHaveAccessibleName(language.busy);

      expect(await boxes(parts)).toBe(before);
      const fits = await button.evaluate((element) => {
        const inner = element.querySelectorAll("[data-submit-label] > span");
        const room = element.clientWidth;
        return (
          element.scrollWidth <= room &&
          element.scrollHeight <= element.clientHeight &&
          Array.from(inner).every((span) => span.getBoundingClientRect().height < 30 && span.scrollWidth <= room)
        );
      });
      expect(fits).toBe(true);
    });
  }
}
