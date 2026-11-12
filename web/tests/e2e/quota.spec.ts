import { expect, test } from "@playwright/test";

import { fulfill, ID, serveAnalysis, view } from "./fake-api";

const RESETS_AT = "2026-11-13T00:00:00+00:00";

function quota(kind: string, limit: number | null, used: number) {
  let remaining: number | null = null;
  if (limit !== null) {
    remaining = limit - used;
  }
  return { kind, limit, used, remaining, resets_at: RESETS_AT };
}

test("the header counts what is left and sends a solved ALTCHA with each analysis", async ({ page }) => {
  let answers = [quota("anonymous", 3, 0), quota("anonymous", 3, 1)];
  await page.route("**/api/quota", async (route) => {
    await fulfill(route, 200, answers[0]);
  });
  let altcha: string | null = null;
  await page.route("**/api/analyses", async (route) => {
    altcha = route.request().headers()["x-altcha"] ?? null;
    answers = answers.slice(1);
    await fulfill(route, 202, { id: ID, state: "queued", cache_only: false });
  });
  await serveAnalysis(page, [view("queued", null)]);
  await page.goto("/fr");
  await expect(page.getByTestId("quota-counter")).toContainText("3 analyses restantes aujourd'hui");
  await expect(page.getByTestId("shared-network")).toBeVisible();
  await page.getByRole("button", { name: "Analyser uvx mcp-server-fetch" }).click();
  await expect(page).toHaveURL(`/fr/analyses/${ID}`);
  await expect(page.getByTestId("quota-counter")).toContainText("2 analyses restantes aujourd'hui");
  expect(altcha).not.toBeNull();
  expect(String(altcha).length).toBeGreaterThan(20);
});

test("a used-up quota shows no verdict, offers an account and keeps the cache open", async ({ page }) => {
  await page.route("**/api/quota", async (route) => {
    await fulfill(route, 200, quota("anonymous", 3, 3));
  });
  await serveAnalysis(page, [view("quota_exhausted", null, { cache_only: true })]);
  await page.goto(`/fr/analyses/${ID}`);
  const panel = page.getByTestId("quota-exhausted");
  await expect(panel).toContainText("Les MCP déjà analysés restent consultables.");
  await expect(page.getByTestId("quota-create-account")).toHaveAttribute("href", "/fr/account/sign-up");
  await expect(page.locator("[data-verdict]")).toHaveCount(0);
  await expect(page.getByText("NON VÉRIFIÉ")).toHaveCount(0);
  await expect(page.getByTestId("quota-counter")).toContainText("Aucune analyse restante aujourd'hui");
});

test("the admin sees no limit", async ({ page }) => {
  await page.route("**/api/quota", async (route) => {
    await fulfill(route, 200, quota("admin", null, 0));
  });
  await page.goto("/fr");
  await expect(page.getByTestId("quota-counter")).toHaveText("Admin : sans limite");
});

test("too many requests says how long to wait", async ({ page }) => {
  await page.route("**/api/analyses", async (route) => {
    await route.fulfill({
      status: 429,
      contentType: "application/json",
      headers: { "Retry-After": "120" },
      body: JSON.stringify({ error: { code: "burst_limit", params: { retry_after: "120", minutes: "2" } } }),
    });
  });
  await page.goto("/fr");
  await page.getByRole("button", { name: "Analyser uvx mcp-server-fetch" }).click();
  await expect(page.locator("#home-error")).toHaveText("Trop de demandes en peu de temps. Réessaie dans 2 minutes.");
});
