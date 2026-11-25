import type { Page } from "@playwright/test";

import { expect, test } from "./test";

import { ID, serveAnalysis } from "./fake-api";
import { reportView } from "./reports";

const PHONE_SIZES = [
  { width: 390, height: 844 },
  { width: 844, height: 390 },
] as const;
const ALL_SIZES = [...PHONE_SIZES, { width: 1280, height: 800 }] as const;
const BAR_MAX = 64;
const QUOTA = { kind: "anonymous", limit: 3, used: 1, remaining: 2, resets_at: "2026-11-26T00:00:00Z" };
const TAB_LIMIT = 65;

async function withQuota(page: Page): Promise<void> {
  await page.route("**/api/quota", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTA) });
  });
}

async function stuckBottom(page: Page): Promise<number> {
  return page.evaluate(() => {
    let bottom = 0;
    for (const element of document.querySelectorAll("[data-header-stuck]")) {
      const style = getComputedStyle(element);
      if (style.display !== "none" && (style.position === "sticky" || style.position === "fixed")) {
        bottom = Math.max(bottom, element.getBoundingClientRect().bottom);
      }
    }
    return bottom;
  });
}

type FocusPlace = { name: string; inHeader: boolean; top: number; bottom: number; viewport: number };

async function focusPlace(page: Page): Promise<FocusPlace | null> {
  return page.evaluate(async () => {
    const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
    let previous = "";
    let stable = 0;
    for (let count = 0; count < 240 && stable < 8; count += 1) {
      await frame();
      const element = document.activeElement;
      const key = `${element?.getBoundingClientRect().top} ${window.scrollY}`;
      if (key === previous) {
        stable += 1;
      } else {
        stable = 0;
      }
      previous = key;
    }
    const element = document.activeElement;
    if (element === null || element === document.body) {
      return null;
    }
    const box = element.getBoundingClientRect();
    return {
      name: `${element.tagName} ${(element.textContent ?? "").trim().slice(0, 40)}`,
      inHeader: element.closest("[data-header-stuck]") !== null || getComputedStyle(element).position === "fixed",
      top: Math.round(box.top),
      bottom: Math.round(box.bottom),
      viewport: window.innerHeight,
    };
  });
}

async function hiddenWhileTabbing(page: Page, key: "Tab" | "Shift+Tab"): Promise<string[]> {
  const hidden: string[] = [];
  for (let step = 0; step < TAB_LIMIT; step += 1) {
    await page.keyboard.press(key);
    const place = await focusPlace(page);
    if (place === null || place.inHeader) {
      continue;
    }
    const bottom = await stuckBottom(page);
    if (place.top < Math.floor(bottom) || place.top >= place.viewport) {
      hidden.push(`${place.name} top=${place.top} bottom=${place.bottom} header=${bottom}`);
    }
  }
  return hidden;
}

for (const size of PHONE_SIZES) {
  test(`on a phone, ${size.width}x${size.height}, the header is a bar of ${BAR_MAX} px at most and the field scrolls away`, async ({ page }) => {
    await page.setViewportSize(size);
    await withQuota(page);
    await serveAnalysis(page, [reportView("orange")]);
    await page.goto(`/fr/analyses/${ID}`);
    await expect(page.locator("[data-verdict]")).toBeVisible();
    const bar = page.locator("[data-phone-bar]");
    await expect(bar).toBeVisible();
    expect((await bar.boundingBox())?.height).toBeLessThanOrEqual(BAR_MAX);
    expect(await stuckBottom(page)).toBeLessThanOrEqual(BAR_MAX);
    await expect(page.getByTestId("quota-compact")).toHaveText("2/32 analyses restantes aujourd'hui");
    await page.mouse.wheel(0, 1500);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
    expect(await stuckBottom(page)).toBeLessThanOrEqual(BAR_MAX);
    await expect(page.locator("#header-input")).not.toBeInViewport();
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollPaddingTop)).toBe(`${BAR_MAX}px`);
  });
}

test("on a computer, the header keeps its place and its height", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await withQuota(page);
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/fr/analyses/${ID}`);
  await expect(page.locator("[data-verdict]")).toBeVisible();
  await expect(page.locator("[data-phone-bar]")).toBeHidden();
  const header = page.locator("#site-header");
  expect(await header.evaluate((element) => getComputedStyle(element).position)).toBe("sticky");
  const boxes = await header.evaluate((element) =>
    Array.from(element.querySelectorAll("a, input, button"))
      .map((item) => item.getBoundingClientRect())
      .filter((box) => box.width > 0)
      .slice(0, 8)
      .map((box) => [box.x, box.y, box.width, box.height].map((value) => Math.round(value)).join(",")),
  );
  expect(boxes).toEqual([
    "74,16,131,44",
    "229,12,356,48",
    "593,12,123,48",
    "743,16,81,44",
    "826,16,53,44",
    "881,16,74,44",
    "977,16,43,44",
    "1022,16,41,44",
  ]);
  const height = await header.evaluate((element) => element.getBoundingClientRect().height);
  expect(height).toBeLessThanOrEqual(110);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollPaddingTop)).toBe(`${Math.ceil(height)}px`);
});

for (const size of ALL_SIZES) {
  test(`tabbing forward and backward on a report, ${size.width}x${size.height}, never hides the focus under the header`, async ({ page }) => {
    await page.setViewportSize(size);
    await withQuota(page);
    await serveAnalysis(page, [reportView("orange")]);
    test.setTimeout(180_000);
    await page.goto(`/fr/analyses/${ID}`);
    await expect(page.locator("[data-verdict]")).toBeVisible();
    expect(await hiddenWhileTabbing(page, "Tab")).toEqual([]);
    expect(await hiddenWhileTabbing(page, "Shift+Tab")).toEqual([]);
  });
}

test("the menu opens and closes with the keyboard, gives the focus back, and traps nothing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await withQuota(page);
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/fr/analyses/${ID}`);
  const button = page.getByRole("button", { name: "Menu" });
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(button).toHaveAttribute("aria-expanded", "true");
  const menu = page.locator("#phone-menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("group", { name: "Thème d'affichage" })).toBeVisible();
  await expect(menu.getByRole("navigation", { name: "Langue" })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Se connecter" })).toBeVisible();
  await expect(menu.getByTestId("quota-counter")).toContainText("2 analyses restantes aujourd'hui");
  await page.keyboard.press("Tab");
  await expect(menu.locator(":focus")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(menu).toBeVisible();
  const targets = await menu.locator("a, button").all();
  for (const target of targets) {
    const box = await target.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
  for (let step = 0; step < targets.length; step += 1) {
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Tab");
  await expect(page.locator("#header-input")).toBeFocused();
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Shift+Tab");
  await expect(button).toBeFocused();
});

test("a click outside the menu closes it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/fr/analyses/${ID}`);
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.locator("#phone-menu")).toBeVisible();
  await page.mouse.click(200, 700);
  await expect(page.locator("#phone-menu")).toHaveCount(0);
});

for (const path of ["/fr", `/fr/analyses/${ID}`]) {
  test(`NEW ANALYSIS puts the focus in the field, ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await serveAnalysis(page, [reportView("orange")]);
    await page.goto(path);
    await expect(page.locator("#home-input, [data-verdict]").first()).toBeVisible();
    await page.mouse.move(200, 400);
    await page.mouse.wheel(0, 2000);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
    await page.getByRole("button", { name: "Nouvelle analyse" }).click();
    const field = page.locator("#home-input, #header-input");
    await expect(field).toBeFocused();
    await expect(field).toBeInViewport();
    const top = await field.evaluate((element) => element.getBoundingClientRect().top);
    expect(top).toBeGreaterThanOrEqual(BAR_MAX);
  });
}
