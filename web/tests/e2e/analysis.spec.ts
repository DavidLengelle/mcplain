import { expect, test } from "@playwright/test";

import { fulfill, ID, SECOND_ID, serveAnalysis, view } from "./fake-api";
import { reportView } from "./reports";

test("typing, then following, then an orange report", async ({ page }) => {
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: ID, state: "queued" });
  });
  await serveAnalysis(page, [view("queued", null), view("fetching", null), view("analyzing", null), reportView("orange")]);

  await page.goto("/");
  await page.getByRole("button", { name: "Fill the field with uvx mcp-server-fetch" }).click();
  await expect(page.getByLabel("MCP server to check")).toHaveValue("uvx mcp-server-fetch");
  await page.getByLabel("MCP server to check").fill("  uvx weather-demo  ");
  await page.getByRole("button", { name: "Analyze", exact: true }).click();

  await expect(page).toHaveURL(`/analyses/${ID}`);
  await expect(page.locator("[data-verdict]")).toBeVisible();
  expect(sent).toEqual({ input: "uvx weather-demo" });
  await expect(page.locator('[data-verdict-word="orange"]')).toHaveText("TO CHECK");
  await expect(page.locator('[data-gauge="orange"]')).toHaveAttribute("aria-label", "Verdict gauge: TO CHECK");
  await expect(page.locator('[data-lamp="files_write"]')).toHaveAttribute("data-state", "on");
  await expect(page.getByRole("heading", { name: "THE 14 TOOLS" })).toBeVisible();
});

test("the header field starts an analysis from any page", async ({ page }) => {
  let sent: unknown = null;
  await serveAnalysis(page, [reportView("green")]);
  await serveAnalysis(page, [view("queued", null)], SECOND_ID);
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: SECOND_ID, state: "queued" });
  });
  await page.goto(`/analyses/${ID}`);
  await page.getByLabel("Link of the MCP server to analyze").fill("npx -y other-server");
  await page.getByRole("button", { name: "ANALYZE", exact: true }).click();
  await expect(page).toHaveURL(`/analyses/${SECOND_ID}`);
  expect(sent).toEqual({ input: "npx -y other-server" });
});

test("a red report shows the original passage and its place", async ({ page }) => {
  await serveAnalysis(page, [reportView("red")]);
  await page.goto(`/analyses/${ID}`);

  await expect(page.locator('[data-verdict-word="red"]')).toHaveText("DANGER");
  await expect(page.locator('[data-lamp="internet"]')).toHaveAttribute("data-state", "danger");
  const note = page.locator('[data-sheet-alert="R05"]');
  await expect(note).toContainText("Every e-mail also goes");
  await expect(note.locator("[data-raw-text]").first()).toBeVisible();
});

test("a failed analysis is gray, says why, says it is not safe, and can run again", async ({ page }) => {
  await serveAnalysis(page, [reportView("failed")]);
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: SECOND_ID, state: "queued" });
  });
  await serveAnalysis(page, [view("queued", null)], SECOND_ID);
  await page.goto(`/analyses/${ID}`);

  const block = page.locator("[data-verdict]");
  await expect(page.locator('[data-verdict-word="gray"]')).toHaveText("NOT VERIFIED");
  await expect(block).toContainText("This does not mean this MCP is safe");
  await expect(page.locator("[data-needle]")).toHaveCount(0);
  await page.getByRole("button", { name: "Run again" }).click();
  await expect(page).toHaveURL(`/analyses/${SECOND_ID}`);
  expect(sent).toEqual({ input: "npx -y @mcplain-demo/this-package-does-not-exist" });
});

test("an unsupported language is gray and names the language", async ({ page }) => {
  await serveAnalysis(page, [reportView("go")]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator('[data-verdict-word="gray"]')).toBeVisible();
  await expect(page.locator("#verdict-title")).toContainText("go");
});

test("a list of servers shows no verdict and sends select when one is chosen", async ({ page }) => {
  await serveAnalysis(page, [reportView("multiple")]);
  await serveAnalysis(page, [view("queued", null)], SECOND_ID);
  let sent: unknown = null;
  await page.route("**/api/analyses", async (route) => {
    sent = route.request().postDataJSON();
    await fulfill(route, 202, { id: SECOND_ID, state: "queued" });
  });
  await page.goto(`/analyses/${ID}`);

  await expect(page.getByText("Nothing has been analyzed yet: choose one.")).toBeVisible();
  await expect(page.locator("[data-verdict]")).toHaveCount(0);
  await page.locator("[data-candidates] button").first().click();
  await expect(page).toHaveURL(`/analyses/${SECOND_ID}`);
  const body = sent as { input?: string; select?: string } | null;
  expect(body?.input).toBe("https://github.com/modelcontextprotocol/servers");
  expect(typeof body?.select).toBe("string");
});

test("a list of links says so and shows no verdict", async ({ page }) => {
  await serveAnalysis(page, [reportView("awesome")]);
  await page.goto(`/fr/analyses/${ID}`);
  await expect(page.locator("[data-link-list]")).toContainText("C'est une liste de liens, pas un MCP.");
  await expect(page.locator("[data-link-list]")).toContainText("Choisis-en un et colle son lien.");
  await expect(page.locator("[data-verdict]")).toHaveCount(0);
});

test("the language button switches the report to French", async ({ page }) => {
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.getByRole("heading", { name: "IN PLAIN WORDS" })).toBeVisible();

  await page.getByRole("navigation", { name: "Language" }).getByRole("link", { name: /FR/ }).click();
  await expect(page).toHaveURL(`/fr/analyses/${ID}`);
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("heading", { name: "EN CLAIR" })).toBeVisible();
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
  await expect(page.locator('[data-verdict-word="gray"]')).toBeVisible();
  await expect(page.locator("[data-verdict]")).toContainText("This does not mean this MCP is safe.");
});

test("an API that answers something strange gives gray not verified", async ({ page }) => {
  await page.route(`**/api/analyses/${ID}`, (route) => fulfill(route, 200, { ...reportView("green"), state: "finished" }));
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator('[data-verdict-word="gray"]')).toBeVisible();
  await expect(page.locator('[data-verdict-word="green"]')).toHaveCount(0);
});

test("a report without its lamps is gray not verified", async ({ page }) => {
  const broken = reportView("green") as { result: { servers: { lamps: unknown }[] } };
  broken.result.servers[0].lamps = [];
  await page.route(`**/api/analyses/${ID}`, (route) => fulfill(route, 200, broken));
  await page.goto(`/analyses/${ID}`);
  await expect(page.locator('[data-verdict-word="gray"]')).toBeVisible();
  await expect(page.locator('[data-verdict-word="green"]')).toHaveCount(0);
});

test("after three minutes the analysis is gray: too long, run again", async ({ page }) => {
  await page.clock.install();
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto(`/analyses/${ID}`);
  await expect(page.getByRole("status")).toHaveText("Current step: Waiting in the queue");
  await page.clock.fastForward("03:05");
  const block = page.locator("[data-verdict]");
  await expect(block).toContainText("The analysis is taking too long.");
  await expect(block).toContainText("This does not mean this MCP is safe.");
  await expect(page.getByRole("button", { name: "Run again" })).toBeVisible();
});

test("the home page is usable with the keyboard, with a visible focus", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  const outline = await focused.evaluate((element) => window.getComputedStyle(element).outlineStyle);
  expect(outline).not.toBe("none");
});
