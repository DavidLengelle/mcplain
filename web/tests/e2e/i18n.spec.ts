import { settle, watchConsole } from "./console-watch";
import { expect, test } from "./test";

test("an English browser stays on / in English", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("MCP servers, explained before you install them.");
});

test.describe("with a French browser", () => {
  test.use({ locale: "fr-FR" });

  test("is redirected to /fr", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/fr");
    await expect(page.locator("html")).toHaveAttribute("lang", "fr");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Les serveurs MCP, expliqués avant que tu les installes.",
    );
  });
});

test("the language button switches the language and keeps the page", async ({ page, context }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Language" }).getByRole("link", { name: /FR/ }).click();
  await expect(page).toHaveURL("/fr");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await page.getByRole("navigation", { name: "Langue" }).getByRole("link", { name: /EN/ }).click();
  await expect(page).toHaveURL("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  const cookies = await context.cookies();
  expect(cookies.map((cookie) => cookie.name).filter((name) => name !== "NEXT_LOCALE")).toEqual([]);
});

test("an unknown page is a localized 404", async ({ page }) => {
  const response = await page.goto("/fr/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page introuvable");
});

test("the footer names the license and links to the source code", async ({ page }) => {
  await page.goto("/fr");
  const footer = page.locator("footer");
  await expect(footer).toContainText("Logiciel libre sous licence AGPL-3.0");
  await expect(footer.getByRole("link", { name: "Code source" })).toHaveAttribute(
    "href",
    "https://github.com/DavidLengelle/mcplain",
  );
});

const QUOTA = { kind: "anonymous", limit: 3, used: 0, remaining: 3, resets_at: "2026-11-26T00:00:00Z" };

test.describe("the language links, with a French browser", () => {
  test.use({ locale: "fr-FR" });

  test("EN switches to English, sets the cookie, is kept on the next visit, without any console error", async ({ page, context }) => {
    await page.route("**/api/quota", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTA) });
    });
    const problems = watchConsole(page);
    await page.goto("/");
    await expect(page).toHaveURL("/fr");
    await page.getByRole("navigation", { name: "Langue" }).getByRole("link", { name: /EN/ }).click();
    await expect(page).toHaveURL("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    const cookie = (await context.cookies()).find((item) => item.name === "NEXT_LOCALE");
    expect(cookie?.value).toBe("en");
    await settle(page);
    await page.goto("/");
    await expect(page).toHaveURL("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.getByRole("navigation", { name: "Language" }).getByRole("link", { name: /EN/ }).click();
    await expect(page).toHaveURL("/");
    await settle(page);
    expect(problems).toEqual([]);
  });
});

test("an English page links its own language without the /en prefix, and never prefetches /en", async ({ page }) => {
  await page.route("**/api/quota", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUOTA) });
  });
  const problems = watchConsole(page);
  await page.goto("/");
  const links = page.getByRole("navigation", { name: "Language" }).getByRole("link");
  await expect(links.filter({ hasText: "EN" })).toHaveAttribute("href", "/");
  await expect(links.filter({ hasText: "FR" })).toHaveAttribute("href", "/fr");
  await settle(page);
  expect(problems).toEqual([]);
});
