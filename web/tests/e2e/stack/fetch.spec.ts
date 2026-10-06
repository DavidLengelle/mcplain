import { expect, test } from "@playwright/test";

test("uvx mcp-server-fetch gives an orange report with O01", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("MCP server to check").fill("uvx mcp-server-fetch");
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect(page).toHaveURL(/\/analyses\/[0-9a-f-]{36}$/);
  const word = page.locator("[data-verdict-word]");
  await expect(word).toBeVisible({ timeout: 150_000 });
  await expect(word).toHaveText("TO CHECK");
  await expect(page.locator('[data-point="O01"]').first()).toContainText("Can reach any website");
  await expect(page.locator('[data-lamp="internet"]')).toHaveAttribute("data-state", "on");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
