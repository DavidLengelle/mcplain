import { expect, test } from "@playwright/test";

const FETCH = "uvx mcp-server-fetch==2026.11.11";

test("uvx mcp-server-fetch 2026.11.11 gives an orange report with O01, O04 and O08", async ({ page }) => {
  await page.goto("/");
  await page.locator("#home-input").fill(FETCH);
  await page.locator("#analyser button[type=submit]").click();
  await expect(page).toHaveURL(/\/analyses\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  const word = page.locator("[data-verdict-word]");
  await expect(word).toBeVisible({ timeout: 150_000 });
  await expect(word).toHaveText("TO CHECK");
  await expect(page.locator('[data-point="O01"]').first()).toContainText("Can reach any website");
  await expect(page.locator('[data-point="O04"]')).not.toHaveCount(0);
  await expect(page.locator('[data-point="O08"]')).not.toHaveCount(0);
  await expect(page.locator('[data-lamp="internet"]')).toHaveAttribute("data-state", "on");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
