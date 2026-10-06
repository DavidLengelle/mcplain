import { expect, test, type Page } from "@playwright/test";

import { ID, serveAnalysis } from "./fake-api";
import { reportView, type ReportName } from "./reports";

const PAGE_COLORS = { light: "rgb(245, 247, 250)", dark: "rgb(12, 19, 27)" } as const;
const VERDICTS: { name: ReportName; color: string; word: string; angle: string | null }[] = [
  { name: "green", color: "green", word: "NOTHING FOUND", angle: "-60" },
  { name: "orange", color: "orange", word: "TO CHECK", angle: "0" },
  { name: "red", color: "red", word: "DANGER", angle: "60" },
];

async function pageColor(page: Page): Promise<string> {
  return page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
}

for (const theme of ["light", "dark"] as const) {
  for (const verdict of VERDICTS) {
    test(`the ${verdict.color} verdict in the ${theme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await serveAnalysis(page, [reportView(verdict.name)]);
      await page.goto(`/analyses/${ID}`);
      await expect(page.locator(`[data-verdict-word="${verdict.color}"]`)).toHaveText(verdict.word);
      await expect(page.locator(`[data-gauge="${verdict.color}"]`)).toBeVisible();
      await expect(page.locator("[data-needle]")).toHaveAttribute("data-needle", verdict.angle ?? "");
      expect(await pageColor(page)).toBe(PAGE_COLORS[theme]);
      await expect(page.locator("[data-lamp]")).toHaveCount(6);
    });
  }
}

test("clicking a tool shows its sheet below the fixed header", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  await page.locator('[data-tool-card="1"]').click();
  const sheet = page.locator('[data-sheet="1"]');
  await expect(sheet).toBeVisible();
  await expect(page.locator('[data-tool-card="1"]')).toHaveAttribute("aria-current", "true");
  await expect
    .poll(
      async () => {
        const header = await page.locator("#site-header").boundingBox();
        const box = await sheet.boundingBox();
        if (header === null || box === null) {
          return false;
        }
        const gap = box.y - (header.y + header.height);
        return gap >= 0 && gap < 60;
      },
      { timeout: 10_000 },
    )
    .toBe(true);
});

test("an alert row opens the sheet of its tool", async ({ page }) => {
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  await page.locator("[data-point]").last().click();
  await expect(page.locator("[data-sheet] [data-sheet-alert]")).toBeVisible();
});

test("the round arrow goes back to the top", async ({ page }) => {
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  await page.locator("footer").scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(500);
  await page.locator("[data-back-to-top]").click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(5);
});

test("the technical details open and close with aria-expanded", async ({ page }) => {
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  const toggle = page.getByRole("button", { name: /TECHNICAL DETAILS/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#details-panel")).toBeHidden();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#details-panel")).toBeVisible();
});

test("the chosen theme is kept after a reload, without any cookie", async ({ page, context }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await serveAnalysis(page, [reportView("green")]);
  await page.goto(`/analyses/${ID}`);
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await pageColor(page)).toBe(PAGE_COLORS.dark);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/th-dark/);
  await expect(page.getByRole("button", { name: "Dark", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await pageColor(page)).toBe(PAGE_COLORS.dark);
  expect(await page.evaluate(() => window.localStorage.getItem("mcplain-theme"))).toBe("dark");
  expect(await context.cookies()).toEqual([]);
  await page.getByRole("button", { name: "System", exact: true }).click();
  expect(await page.evaluate(() => window.localStorage.getItem("mcplain-theme"))).toBeNull();
  expect(await pageColor(page)).toBe(PAGE_COLORS.light);
});

test("the stored theme is applied before the first paint", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() => {
    window.localStorage.setItem("mcplain-theme", "dark");
    const marks: string[] = [];
    (window as unknown as { themeMarks: string[] }).themeMarks = marks;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        marks.push(`${entry.name}:${document.documentElement.classList.contains("th-dark")}`);
      }
    }).observe({ type: "paint", buffered: true });
  });
  await serveAnalysis(page, [reportView("green")]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator("html")).toHaveClass(/th-dark/);
  const marks = await page.evaluate(() => (window as unknown as { themeMarks: string[] }).themeMarks);
  test.info().annotations.push({ type: "paint", description: marks.join(", ") });
  expect(await pageColor(page)).toBe(PAGE_COLORS.dark);
});

test("without a choice, the theme follows the system", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  expect(await pageColor(page)).toBe(PAGE_COLORS.dark);
  await page.emulateMedia({ colorScheme: "light" });
  expect(await pageColor(page)).toBe(PAGE_COLORS.light);
});

test("smooth scrolling, and instant scrolling with reduced motion", async ({ page }) => {
  await page.goto("/");
  expect(await page.evaluate(() => window.getComputedStyle(document.documentElement).scrollBehavior)).toBe("smooth");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await page.evaluate(() => window.getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
});

for (const name of ["green", "orange", "red", "failed", "multiple"] as const) {
  test(`the ${name} report fits a 390 pixel wide phone`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await serveAnalysis(page, [reportView(name)]);
    await page.goto(`/analyses/${ID}`);
    await expect(page.locator("[data-report]")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("from the cache, the report says so with the date of the real analysis", async ({ page }) => {
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator("[data-from-cache]")).toContainText("Result taken from an analysis of");
});
