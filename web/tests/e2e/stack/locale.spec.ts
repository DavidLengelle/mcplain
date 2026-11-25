import { expect, test } from "@playwright/test";

import { settle, watchConsole } from "../console-watch";

import { site } from "./helpers";

test.describe("on the Docker stack, in plain http, with a French browser", () => {
  test.use({ locale: "fr-FR" });

  test("EN switches to English without any console error, and the choice is kept", async ({ page, context, baseURL }) => {
    const problems = watchConsole(page);
    await page.goto(site(baseURL, "/fr"));
    await settle(page);
    await page.getByRole("navigation", { name: "Langue" }).getByRole("link", { name: /EN/ }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    expect(new URL(page.url()).pathname).toBe("/");
    const cookie = (await context.cookies()).find((item) => item.name === "NEXT_LOCALE");
    expect(cookie?.value).toBe("en");
    await settle(page);
    await page.goto(site(baseURL, "/"));
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    expect(new URL(page.url()).pathname).toBe("/");
    await settle(page);
    await page.getByRole("navigation", { name: "Language" }).getByRole("link", { name: /EN/ }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await settle(page);
    expect(problems).toEqual([]);
  });
});
