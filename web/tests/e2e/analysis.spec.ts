import { expect, test } from "@playwright/test";

import {
  failedView,
  fulfill,
  ID,
  multipleView,
  orangeView,
  redView,
  SECOND_ID,
  serveAnalysis,
  view,
} from "./fake-api";

test("typing, then following, then an orange report", async ({ page }) => {
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: ID, state: "queued" });
  });
  await serveAnalysis(page, [view("queued", null), view("fetching", null), view("analyzing", null), orangeView()]);

  await page.goto("/");
  await page.getByRole("button", { name: "Fill the field with uvx mcp-server-fetch" }).click();
  await expect(page.getByLabel("MCP server to check")).toHaveValue("uvx mcp-server-fetch");
  await page.getByLabel("MCP server to check").fill("  uvx weather-demo  ");
  await page.getByRole("button", { name: "Analyze" }).click();

  await expect(page).toHaveURL(`/analyses/${ID}`);
  await expect(page.getByRole("status")).toHaveText(/Current step: (Waiting in the queue|Downloading the code|Reading the code)/);
  const panel = page.locator("[data-verdict-panel]");
  await expect(panel).toBeVisible();
  expect(sent).toEqual({ input: "uvx weather-demo" });
  await expect(panel.locator('[data-verdict="orange"]')).toHaveText("Orange");
  await expect(panel.locator('[data-verdict="orange"] svg')).toBeVisible();
  const card = page.locator('[data-tool="fetch_page"]');
  await expect(card.getByText("(according to the author)")).toBeVisible();
  await expect(card.getByText("Fetches a page and returns its text.")).toBeVisible();
  await expect(card.getByText("network access")).toBeVisible();
  await expect(card.locator('[data-rule="O01"]')).toContainText("Can contact any address");
  await expect(page.getByText("https://api.weather.example/v1")).toBeVisible();
  await expect(page.locator("main a")).toHaveCount(0);
});

test("a red report shows the original passage and its place", async ({ page }) => {
  await serveAnalysis(page, [redView()]);
  await page.goto(`/analyses/${ID}`);

  await expect(page.locator('[data-verdict-panel] [data-verdict="red"]')).toHaveText("Red");
  const alert = page.locator('[data-rule="R01"]');
  await expect(alert).toContainText("Invisible text");
  await expect(alert).toContainText("weather_demo/server.py:12");
  const passage = alert.locator("bdi").filter({ hasText: "Returns the forecast for a city." }).last();
  await expect(passage).toBeVisible();
  await expect(passage.locator('[data-invisible="U+200B"]')).toHaveCount(2);
  expect(await passage.textContent()).not.toContain("\u200B");
});

test("a failed analysis is gray, says why, and says it is not safe", async ({ page }) => {
  await serveAnalysis(page, [failedView()]);
  await page.goto(`/analyses/${ID}`);

  const panel = page.locator("[data-verdict-panel]");
  await expect(panel.locator('[data-verdict="gray"]')).toHaveText("Gray");
  await expect(panel).toContainText("That does not mean it is safe.");
  await expect(panel).toContainText("The analysis failed");
  await expect(panel).toContainText("The analysis took too long and was stopped.");
});

test("a list of servers sends select when one is chosen", async ({ page }) => {
  await serveAnalysis(page, [multipleView()]);
  await serveAnalysis(page, [orangeView()], SECOND_ID);
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: SECOND_ID, state: "queued" });
  });
  await page.goto(`/analyses/${ID}`);

  await expect(page.getByRole("heading", { name: "Several servers were found" })).toBeVisible();
  await page.getByRole("button", { name: /servers\/beta/ }).click();
  await expect(page).toHaveURL(`/analyses/${SECOND_ID}`);
  expect(sent).toEqual({ input: "https://github.com/example/monorepo", select: "servers/beta" });
});

test("the language button switches the report to French", async ({ page }) => {
  await serveAnalysis(page, [orangeView()]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.getByRole("heading", { name: "What each tool does" })).toBeVisible();

  await page.getByRole("navigation", { name: "Language" }).getByRole("link", { name: /FR/ }).click();
  await expect(page).toHaveURL(`/fr/analyses/${ID}`);
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("heading", { name: "Ce que fait chaque outil" })).toBeVisible();
  await expect(page.locator('[data-tool="fetch_page"]')).toContainText("selon l'auteur");
});

test("an unknown analysis is a 404 page", async ({ page }) => {
  await page.route(`**/api/analyses/${ID}`, (route) =>
    fulfill(route, 404, { error: { code: "api.analysis_not_found", params: {} } }),
  );
  await page.goto(`/analyses/${ID}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
});

test("a malformed identifier is a 404 without any call to the API", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/**", async (route) => {
    calls += 1;
    await route.abort();
  });
  const response = await page.goto("/analyses/not-a-uuid");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
  expect(calls).toBe(0);
});

test("an API that does not answer gives gray not verified, never green", async ({ page }) => {
  await page.route(`**/api/analyses/${ID}`, (route) => route.abort("connectionrefused"));
  await page.goto(`/analyses/${ID}`);
  const panel = page.locator("[data-verdict-panel]");
  await expect(panel.locator('[data-verdict="gray"]')).toBeVisible();
  await expect(panel).toContainText("Not verified");
  await expect(panel).toContainText("That does not mean it is safe.");
});

test("an API that answers something strange gives gray not verified", async ({ page }) => {
  await page.route(`**/api/analyses/${ID}`, (route) => fulfill(route, 200, { ...orangeView(), state: "finished" }));
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator('[data-verdict-panel] [data-verdict="gray"]')).toBeVisible();
  await expect(page.locator('[data-verdict="green"]')).toHaveCount(0);
});

test("after three minutes the analysis is gray: too long, try again", async ({ page }) => {
  await page.clock.install();
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.getByRole("status")).toHaveText("Current step: Waiting in the queue");
  await page.clock.fastForward("03:05");
  const panel = page.locator("[data-verdict-panel]");
  await expect(panel).toContainText("Too long");
  await expect(panel).toContainText("That does not mean it is safe.");
});

test("the report fits a 360 pixel wide phone", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await serveAnalysis(page, [redView()]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator("[data-verdict-panel]")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the home page is usable with the keyboard, with a visible focus", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  const outline = await focused.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return `${style.outlineStyle} ${style.boxShadow}`;
  });
  expect(outline).not.toBe("none none");
});
