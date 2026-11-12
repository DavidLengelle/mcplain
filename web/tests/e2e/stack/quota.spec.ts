import { expect, test, type Page } from "@playwright/test";

import { linkOf, psql, resetCounters, screens, site, waitForMail } from "./helpers";

const PASSWORD = "quota password, long enough";
const CACHED = "uvx mcp-server-time";
const NEVER_ANALYZED = "npx -y is-number@7.0.0";
const VERDICT_WAIT = 150_000;

function missingPackage(): string {
  return `npx -y @mcplain-demo/not-there-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6)}`;
}

async function analyze(page: Page, baseURL: string | undefined, input: string) {
  await page.goto(site(baseURL, "/fr"));
  await page.locator("#home-input").fill(input);
  await page.locator("#analyser button[type=submit]").click();
  await expect(page).toHaveURL(/\/fr\/analyses\/[0-9a-f-]{36}$/, { timeout: 30_000 });
}

async function analyzeToTheEnd(page: Page, baseURL: string | undefined, input: string) {
  await analyze(page, baseURL, input);
  await expect(page.locator("[data-verdict-word]")).toBeVisible({ timeout: VERDICT_WAIT });
}

test.beforeEach(() => {
  resetCounters();
});

test.afterEach(() => {
  resetCounters();
});

test("a visitor without account uses 3 analyses, then is offered an account, and the cache stays open", async ({ page, baseURL }) => {
  await analyzeToTheEnd(page, baseURL, CACHED);
  resetCounters();

  await page.goto(site(baseURL, "/fr"));
  await expect(page.getByTestId("quota-counter")).toContainText("3 analyses restantes aujourd'hui");
  await expect(page.getByTestId("shared-network")).toBeVisible();
  await screens(page, baseURL, "/fr", "quota-counter-anonymous", "[data-testid=quota-counter]");

  for (let count = 0; count < 3; count += 1) {
    await analyzeToTheEnd(page, baseURL, missingPackage());
  }
  await page.goto(site(baseURL, "/fr"));
  await expect(page.getByTestId("quota-counter")).toContainText("Aucune analyse restante aujourd'hui");

  await analyze(page, baseURL, NEVER_ANALYZED);
  const exhausted = page.getByTestId("quota-exhausted");
  await expect(exhausted).toBeVisible({ timeout: VERDICT_WAIT });
  await expect(exhausted).toContainText("Les MCP déjà analysés restent consultables.");
  await expect(page.getByTestId("quota-create-account")).toHaveText("Créer un compte");
  await expect(page.locator("[data-verdict]")).toHaveCount(0);
  const exhaustedPath = new URL(page.url()).pathname;
  await screens(page, baseURL, exhaustedPath, "quota-exhausted", "[data-testid=quota-exhausted]");

  await analyzeToTheEnd(page, baseURL, CACHED);
  await expect(page.locator("[data-from-cache]")).toContainText("Cette analyse n'a pas été décomptée.");
  await expect(page.getByTestId("quota-counter")).toContainText("Aucune analyse restante aujourd'hui");
});

test("an account sees its ten analyses, finds them in its history, then clears it", async ({ page, request, baseURL }) => {
  const email = `quota-${Date.now()}@example.com`;
  await page.goto(site(baseURL, "/fr/account/sign-up"));
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CRÉER MON COMPTE" }).click();
  await expect(page.getByTestId("sign-up-done")).toBeVisible({ timeout: 30_000 });
  const verification = await waitForMail(request, email, /Confirme ton adresse/);
  await page.goto(linkOf(verification.text));
  await expect(page.getByTestId("header-account")).toBeVisible();
  const userId = psql(`SELECT id FROM auth."user" WHERE email = '${email}'`).trim();

  await page.goto(site(baseURL, "/fr"));
  await expect(page.getByTestId("quota-counter")).toContainText("10 analyses restantes aujourd'hui", { timeout: 15_000 });
  await expect(page.getByTestId("shared-network")).toHaveCount(0);
  await screens(page, baseURL, "/fr", "quota-counter-account", "[data-testid=quota-counter]");

  await analyzeToTheEnd(page, baseURL, CACHED);
  await expect(page.locator("[data-from-cache]")).toBeVisible();
  await page.goto(site(baseURL, "/fr"));
  await expect(page.getByTestId("quota-counter")).toContainText("10 analyses restantes aujourd'hui");

  await page.goto(site(baseURL, "/fr/account"));
  const entry = page.getByTestId("history-entry").first();
  await expect(entry).toContainText(CACHED);
  await expect(entry).toContainText("depuis le cache");
  await screens(page, baseURL, "/fr/account", "account-history", "[data-testid=history-entry]");
  await page.goto(site(baseURL, "/fr/account"));
  await page.getByRole("button", { name: "EFFACER MON HISTORIQUE" }).click();
  await page.getByRole("button", { name: "OUI, EFFACER" }).click();
  await expect(page.getByTestId("history-empty")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("history-empty")).toBeVisible();
  expect(psql(`SELECT count(*) FROM user_history WHERE user_id = '${userId}'`).trim()).toBe("0");

  await analyzeToTheEnd(page, baseURL, CACHED);
  await page.goto(site(baseURL, "/fr/account"));
  await expect(page.getByTestId("history-entry")).toHaveCount(1);
  await page.getByRole("button", { name: "SUPPRIMER MON COMPTE" }).click();
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "OUI, SUPPRIMER POUR DE BON" }).click();
  await expect(page.getByTestId("account-deleted")).toBeVisible();
  expect(psql(`SELECT count(*) FROM user_history WHERE user_id = '${userId}'`).trim()).toBe("0");
});
