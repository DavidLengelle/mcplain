import { expect, test, type Browser, type Page } from "@playwright/test";

import { cleanUp, psql, resetSignups, screens, signIn, site } from "./helpers";
import { totpCode } from "./totp";

const PASSWORD = "admin password, long enough";
const SIGN_IN_WINDOW_MS = 11_000;
const PERIOD_MS = 30_000;
const addresses: string[] = [];

test.beforeEach(() => {
  resetSignups();
});

test.afterEach(async ({ request }) => {
  await cleanUp(request, addresses.splice(0));
});

async function makeAccount(page: Page, baseURL: string | undefined, email: string, role: string): Promise<void> {
  await page.goto(site(baseURL, "/fr/account/sign-up"));
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CRÉER MON COMPTE" }).click();
  await expect(page.getByTestId("sign-up-done")).toBeVisible({ timeout: 30_000 });
  psql(`DELETE FROM mail_outbox WHERE recipient = '${email}'; UPDATE auth."user" SET "emailVerified" = true, role = '${role}' WHERE email = '${email}';`);
}

async function freshCode(secret: string, used: Set<string>): Promise<string> {
  let code = totpCode(secret);
  while (used.has(code)) {
    await new Promise((resolve) => setTimeout(resolve, PERIOD_MS - (Date.now() % PERIOD_MS) + 500));
    code = totpCode(secret);
  }
  used.add(code);
  return code;
}

async function signOut(page: Page, baseURL: string | undefined): Promise<void> {
  await page.goto(site(baseURL, "/fr/account"));
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByTestId("header-sign-in")).toBeVisible();
}

async function otherPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  return context.newPage();
}

test("the admin turns on two-step verification, signs in with a code then a backup code, blocks and unblocks an account", async ({
  page,
  browser,
  baseURL,
}) => {
  const stamp = Date.now();
  const admin = `admin-9c-${stamp}@example.com`;
  const target = `target-9c-${stamp}@example.com`;
  addresses.push(admin, target);
  const used = new Set<string>();

  await makeAccount(page, baseURL, admin, "admin");
  await signIn(page, baseURL, admin, PASSWORD);
  await expect(page.getByTestId("account-email")).toHaveText(admin, { timeout: 30_000 });
  await expect(page.getByTestId("two-factor-off")).toBeVisible();
  await page.goto(site(baseURL, "/fr/admin"));
  await expect(page.getByTestId("admin-needs-two-factor")).toHaveText("Active la double authentification");
  await expect(page.getByRole("heading", { name: "Comptes", exact: true })).toHaveCount(0);

  await page.goto(site(baseURL, "/fr/account#security"));
  await page.getByRole("button", { name: "ACTIVER LA DOUBLE AUTHENTIFICATION" }).click();
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CONTINUER" }).click();
  const key = (await page.getByTestId("totp-key").textContent()) ?? "";
  expect(key).toMatch(/^([A-Z2-7]{4} )+[A-Z2-7]{1,4}$/);
  const secret = key.replaceAll(" ", "");
  const field = page.getByLabel("Code à 6 chiffres");
  await expect(field).toHaveAttribute("inputmode", "numeric");
  const first = await freshCode(secret, used);
  await field.fill(`${first.slice(0, 3)} ${first.slice(3)}`);
  await page.getByRole("button", { name: "CONFIRMER" }).click();
  await expect(page.getByTestId("backup-codes")).toBeVisible({ timeout: 30_000 });
  const codes = await page.getByTestId("backup-code").allTextContents();
  expect(codes).toHaveLength(10);
  await page.getByRole("button", { name: "J'AI RANGÉ MES CODES" }).click();
  await expect(page.getByTestId("backup-codes")).toHaveCount(0);
  await expect(page.getByTestId("two-factor-on")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("two-factor-on")).toBeVisible();
  await expect(page.getByTestId("backup-codes")).toHaveCount(0);
  await page.goto(site(baseURL, "/fr/admin"));
  await expect(page.getByRole("heading", { name: "Comptes", exact: true })).toBeVisible();
  await screens(page, baseURL, "/fr/admin", "admin-desk", "[data-testid=admin-top-dial]");

  await signOut(page, baseURL);
  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(page, baseURL, admin, PASSWORD);
  await expect(page.getByTestId("two-factor-step")).toBeVisible({ timeout: 30_000 });
  await page.goto(site(baseURL, "/fr/admin"));
  await expect(page.getByTestId("header-sign-in")).toBeVisible();
  await signIn(page, baseURL, admin, PASSWORD);
  await expect(page.getByTestId("two-factor-step")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Code à 6 chiffres").fill(await freshCode(secret, used));
  await page.getByRole("button", { name: "VÉRIFIER" }).click();
  await expect(page.getByTestId("account-email")).toHaveText(admin, { timeout: 30_000 });
  const trusted = (await page.context().cookies()).filter((cookie) => cookie.name.includes("trust_device") && cookie.value !== "");
  expect(trusted).toEqual([]);

  await signOut(page, baseURL);
  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(page, baseURL, admin, PASSWORD);
  await expect(page.getByTestId("two-factor-step")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Utiliser un code de secours" }).click();
  await page.getByLabel("Code de secours").fill(codes[0] ?? "");
  await page.getByRole("button", { name: "VÉRIFIER" }).click();
  await expect(page.getByTestId("account-email")).toHaveText(admin, { timeout: 30_000 });

  const visitor = await otherPage(browser);
  await makeAccount(visitor, baseURL, target, "user");
  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(visitor, baseURL, target, PASSWORD);
  await expect(visitor.getByTestId("account-email")).toHaveText(target, { timeout: 30_000 });

  await page.goto(site(baseURL, "/fr/admin"));
  await page.getByLabel("Adresse e-mail exacte").fill(target);
  await page.getByRole("button", { name: "CHERCHER" }).click();
  await expect(page.getByTestId("admin-account-state")).toHaveText("Actif");
  await page.getByLabel("Motif du blocage (facultatif, vu par l'admin seulement)").fill("test 9c");
  await page.getByRole("button", { name: "BLOQUER CE COMPTE" }).click();
  await expect(page.getByTestId("admin-account-state")).toHaveText(/^Bloqué depuis le /);
  await expect(page.getByTestId("admin-account-reason")).toHaveText("test 9c");

  await visitor.goto(site(baseURL, "/fr/account"));
  await expect(visitor.getByTestId("header-sign-in")).toBeVisible();
  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(visitor, baseURL, target, PASSWORD);
  await expect(visitor.getByText("Ce compte est bloqué.")).toBeVisible({ timeout: 30_000 });
  await expect(visitor.getByText("test 9c")).toHaveCount(0);

  await page.getByRole("button", { name: "Débloquer ce compte" }).click();
  await expect(page.getByTestId("admin-account-state")).toHaveText("Actif");
  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(visitor, baseURL, target, PASSWORD);
  await expect(visitor.getByTestId("account-email")).toHaveText(target, { timeout: 30_000 });
  await visitor.context().close();
});

const NOTE = "stack test 9c-2";

async function adminWithSecondFactor(page: Page, baseURL: string | undefined, email: string, used: Set<string>): Promise<void> {
  await makeAccount(page, baseURL, email, "admin");
  await signIn(page, baseURL, email, PASSWORD);
  await expect(page.getByTestId("account-email")).toHaveText(email, { timeout: 30_000 });
  await page.goto(site(baseURL, "/fr/account#security"));
  await page.getByRole("button", { name: "ACTIVER LA DOUBLE AUTHENTIFICATION" }).click();
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CONTINUER" }).click();
  const secret = ((await page.getByTestId("totp-key").textContent()) ?? "").replaceAll(" ", "");
  await page.getByLabel("Code à 6 chiffres").fill(await freshCode(secret, used));
  await page.getByRole("button", { name: "CONFIRMER" }).click();
  await expect(page.getByTestId("backup-codes")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "J'AI RANGÉ MES CODES" }).click();
  await expect(page.getByTestId("two-factor-on")).toBeVisible();
}

test("the admin reads the dials, enters a statement and is told plainly that a notice cannot be asked while the AI is off", async ({ page, baseURL }) => {
  const admin = `admin-9c2-${Date.now()}@example.com`;
  addresses.push(admin);
  const textId = crypto.randomUUID();
  const sentBefore = psql("SELECT coalesce(sent_at::text, '') FROM balance_alert WHERE id = 1;").trim();
  psql(
    "INSERT INTO ai_texts (id, kind, lang, hash, prompt_version, model, status, reject_reason, analysis_id, created_at, updated_at) " +
      `VALUES ('${textId}', 'notice', 'fr', '${"a".repeat(64)}', 'stack-9c-2', 'stack', 'rejected', 'link', NULL, now(), now());`,
  );
  try {
    await adminWithSecondFactor(page, baseURL, admin, new Set<string>());
    await page.goto(site(baseURL, "/fr/admin"));
    await expect(page.getByTestId("admin-spend-today")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("admin-spend-days").getByRole("listitem")).toHaveCount(30);
    await expect(page.getByTestId("admin-accounts-total")).toBeVisible();
    await page.getByRole("button", { name: "7 j" }).click();
    await expect(page.getByTestId("admin-spend-days").getByRole("listitem")).toHaveCount(7);

    await page.getByLabel("Montant en dollars").fill("9,75");
    await page.getByLabel("Note (facultative)").fill(NOTE);
    await page.getByRole("button", { name: "AJOUTER" }).click();
    await expect(page.getByTestId("admin-credit-entries")).toContainText(NOTE);
    await expect(page.getByTestId("admin-balance-amount")).toBeVisible();
    await expect(page.getByText("Estimation : le vrai solde est dans la console Anthropic.")).toBeVisible();

    const line = page.getByTestId("admin-texts").getByRole("listitem").filter({ hasText: "link" }).first();
    await line.getByRole("button", { name: "Relancer la notice" }).click();
    await line.getByRole("button", { name: "Oui, relancer" }).click();
    await expect(page.getByText("Bloqué : l'IA est coupée, aucune notice n'est demandée.")).toBeVisible();
    expect(psql(`SELECT status FROM ai_texts WHERE id = '${textId}';`).trim()).toBe("rejected");
    await expect(page.getByTestId("admin-journal")).toContainText("Écriture ajoutée");
    await screens(page, baseURL, "/fr/admin", "admin-dashboard", "[data-testid=admin-top-dial]");
  } finally {
    psql(`DELETE FROM ai_texts WHERE id = '${textId}';`);
    psql(`DELETE FROM admin_actions WHERE target_id IN (SELECT id::text FROM credit_entries WHERE note = '${NOTE}'); DELETE FROM credit_entries WHERE note = '${NOTE}';`);
    if (sentBefore === "") {
      psql("UPDATE balance_alert SET sent_at = NULL WHERE id = 1;");
    } else {
      psql(`UPDATE balance_alert SET sent_at = '${sentBefore}' WHERE id = 1;`);
    }
  }
});
