import { expect, test } from "@playwright/test";

test("an English browser stays on / in English", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("MCP servers, explained before you install.");
});

test.describe("with a French browser", () => {
  test.use({ locale: "fr-FR" });

  test("is redirected to /fr", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/fr");
    await expect(page.locator("html")).toHaveAttribute("lang", "fr");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Les serveurs MCP, expliqués avant de les installer.",
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
  await expect(footer).toContainText("Logiciel libre AGPL-3.0");
  await expect(footer.getByRole("link", { name: "Code source" })).toHaveAttribute(
    "href",
    "https://github.com/DavidLengelle/mcplain",
  );
});
