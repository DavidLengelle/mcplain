import { expect, test, type Page } from "@playwright/test";

import { fulfill, ID, serveAnalysis, view } from "./fake-api";

const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;
const CHAPTERS = ["mcp", "usage", "danger", "histoire", "proteger", "lire", "exemple", "limites", "lexique"];

async function headerBottom(page: Page): Promise<number> {
  return page.locator("#site-header").evaluate((header) => header.getBoundingClientRect().bottom);
}

async function settledTop(page: Page, selector: string): Promise<number> {
  let previous = Number.NaN;
  await expect
    .poll(async () => {
      const top = await page.locator(selector).evaluate((element) => Math.round(element.getBoundingClientRect().top));
      const stable = top === previous;
      previous = top;
      return stable;
    })
    .toBe(true);
  return previous;
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`the home page fits ${width} px in the ${theme} theme, without horizontal scroll`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/fr");
      await expect(page.locator("#analyser")).toBeVisible();
      const sizes = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
      expect(sizes[0]).toBeLessThanOrEqual(sizes[1]);
      await expect(page.locator("#site-header input")).toHaveCount(0);
      await expect(page.locator("#analyser [data-lamp]")).toHaveCount(6);
      await expect(page.locator("#analyser [data-gauge]")).toHaveCount(0);
      for (const id of CHAPTERS) {
        await expect(page.locator(`section#${id}`)).toHaveCount(1);
      }
    });
  }
}

test("the tool zone spans the whole width and the examples wrap on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/");
  const band = await page.locator("#analyser").boundingBox();
  expect(band?.x).toBe(0);
  expect(band?.width).toBe(390);
  const examples = page.locator("button[data-example]");
  await expect(examples).toHaveCount(3);
  const tops = await examples.evaluateAll((buttons) => buttons.map((button) => button.getBoundingClientRect().top));
  expect(new Set(tops).size).toBeGreaterThan(1);
  for (const box of await examples.evaluateAll((buttons) => buttons.map((button) => button.getBoundingClientRect().right))) {
    expect(box).toBeLessThanOrEqual(390);
  }
});

test("the header has its field again on a report page", async ({ page }) => {
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto(`/fr/analyses/${ID}`);
  await expect(page.locator("#site-header input")).toHaveCount(1);
});

for (const width of WIDTHS) {
  test(`a chapter of the table of contents stops under the fixed header, ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/fr");
    await page.locator('a[data-toc="danger"]').click();
    await expect(page).toHaveURL(/#danger$/);
    const top = await settledTop(page, "#danger");
    const bottom = await headerBottom(page);
    expect(top).toBeGreaterThanOrEqual(Math.floor(bottom));
    expect(top).toBeLessThan(bottom + 40);
    await expect(page.locator("#h-danger")).toBeInViewport();
  });
}

test("ANALYZE AN MCP brings the visitor back to the big field, with the focus in it", async ({ page }) => {
  await page.goto("/");
  const link = page.getByRole("link", { name: "ANALYZE AN MCP", exact: true });
  await link.scrollIntoViewIfNeeded();
  await link.click();
  await expect(page.locator("#home-input")).toBeFocused();
  await settledTop(page, "#analyser");
  await expect(page.locator("#home-input")).toBeInViewport();
  await page.keyboard.type("uvx mcp-server-time");
  await expect(page.locator("#home-input")).toHaveValue("uvx mcp-server-time");
});

test("a click on an example fills the field and starts the analysis", async ({ page }) => {
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: ID, state: "queued" });
  });
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto("/fr");
  await page.getByRole("button", { name: "Analyser uvx mcp-server-fetch" }).click();
  await expect(page).toHaveURL(`/fr/analyses/${ID}`);
  expect(sent).toEqual({ input: "uvx mcp-server-fetch" });
});

test("the GitHub example sends the whole link, even shown without https://", async ({ page }) => {
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: ID, state: "queued" });
  });
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto("/");
  const example = page.getByRole("button", { name: "Analyze github.com/modelcontextprotocol/servers/tree/main/src/fetch" });
  await expect(example).toHaveText("github.com/modelcontextprotocol/servers/tree/main/src/fetch");
  await example.click();
  await expect(page).toHaveURL(`/analyses/${ID}`);
  expect(sent).toEqual({ input: "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch" });
});

test("the scroll is smooth, and instant with reduced motion", async ({ page }) => {
  await page.goto("/fr");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("smooth");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  await page.locator('a[data-toc="lexique"]').click();
  const top = await page.locator("#lexique").evaluate((element) => element.getBoundingClientRect().top);
  const bottom = await headerBottom(page);
  expect(top).toBeGreaterThanOrEqual(Math.floor(bottom));
  expect(top).toBeLessThan(bottom + 40);
});

test("external links open in a new tab, without opener nor referrer", async ({ page }) => {
  await page.goto("/fr");
  const links = page.locator('main a[href^="http"]');
  await expect(links).toHaveCount(6);
  for (const link of await links.all()) {
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }
});

for (const width of WIDTHS) {
  test(`the big submit button shows its whole text while sending, ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/api/analyses", () => new Promise(() => {}));
    await page.goto("/fr");
    const button = page.locator("#analyser button[type=submit]");
    const before = await button.boundingBox();
    await page.locator("#home-input").fill("uvx mcp-server-fetch");
    await button.click();
    await expect(button).toHaveAccessibleName("ENVOI…");
    expect(await button.boundingBox()).toEqual(before);
    expect(await button.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  });
}

test("every target of the home page is at least 44 px high", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/fr");
  const small = await page
    .locator("main a:not(p a), main button, main input")
    .evaluateAll((elements) =>
      elements
        .filter((element) => element.getBoundingClientRect().height < 44)
        .map((element) => `${element.tagName} ${element.textContent?.slice(0, 40)}`),
    );
  expect(small).toEqual([]);
});
