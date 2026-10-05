import { expect, test } from "@playwright/test";

test("the home page answers", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("MCPlain");
});
