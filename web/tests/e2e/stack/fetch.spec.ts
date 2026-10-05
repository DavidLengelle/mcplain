import { expect, test } from "@playwright/test";

test("uvx mcp-server-fetch gives an orange report with O01", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("MCP server to check").fill("uvx mcp-server-fetch");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page).toHaveURL(/\/analyses\/[0-9a-f-]{36}$/);
  const panel = page.locator("[data-verdict-panel]");
  await expect(panel).toBeVisible({ timeout: 150_000 });
  await expect(panel.locator('[data-verdict="orange"]')).toHaveText("Orange");
  await expect(page.locator('[data-rule="O01"]').first()).toContainText("Can contact any address");
});
