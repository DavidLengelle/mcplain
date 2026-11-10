import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const MAILPIT = process.env.MCPLAIN_MAILPIT_URL ?? "http://127.0.0.1:8025";
const SCREENS = join(__dirname, "..", "..", "..", "test-results", "screens");
const RESULTS = join(__dirname, "..", "..", "..", "test-results");
const PASSWORD = "first password, long enough";
const NEW_PASSWORD = "second password, long enough";
const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;
const LINK = /https?:\/\/\S+/;
const ALTCHA_RUNS = 10;
const MID_PHONE_SLOWDOWN = 4;
const SIGN_IN_WINDOW_MS = 11_000;

function site(baseURL: string | undefined, path: string): string {
  const url = new URL(path, baseURL);
  url.hostname = "localhost";
  return url.toString();
}

type MailSummary = { ID: string; Subject: string; To: { Address: string }[] };

async function waitForMail(request: APIRequestContext, address: string, subject: RegExp): Promise<{ text: string; html: string }> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const listing = await request.get(`${MAILPIT}/api/v1/messages`, { params: { limit: "200" } });
    const body = (await listing.json()) as { messages: MailSummary[] };
    const found = body.messages.find(
      (message) => subject.test(message.Subject) && message.To.some((recipient) => recipient.Address === address),
    );
    if (found !== undefined) {
      const message = (await (await request.get(`${MAILPIT}/api/v1/message/${found.ID}`)).json()) as { Text: string; HTML: string };
      await request.delete(`${MAILPIT}/api/v1/messages`, { data: { IDs: [found.ID] } });
      return { text: message.Text, html: message.HTML };
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`no mail for ${address}`);
}

function linkOf(text: string): string {
  const match = LINK.exec(text);
  if (match === null) {
    throw new Error("the mail has no link");
  }
  return match[0];
}

async function signIn(page: Page, baseURL: string | undefined, email: string, password: string) {
  await page.goto(site(baseURL, "/fr/account/sign-in"));
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(password);
  await page.getByRole("button", { name: "SE CONNECTER" }).click();
}

async function screens(page: Page, baseURL: string | undefined, path: string, name: string, ready: string) {
  mkdirSync(SCREENS, { recursive: true });
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(site(baseURL, path));
      await expect(page.locator(ready).first()).toBeVisible();
      await page.screenshot({ path: join(SCREENS, `${name}-${theme}-${width}.png`), fullPage: true });
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "light" });
}

test("an account is created, verified, used, recovered and deleted", async ({ page, request, baseURL }) => {
  const email = `ada-${Date.now()}@example.com`;

  await screens(page, baseURL, "/fr/account/sign-up", "account-sign-up", "form");
  await page.goto(site(baseURL, "/fr/account/sign-up"));
  await expect(page.getByTestId("header-sign-in")).toBeVisible();
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CRÉER MON COMPTE" }).click();
  await expect(page.getByTestId("sign-up-done")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("ALTCHA")).toHaveCount(0);

  const verification = await waitForMail(request, email, /Confirme ton adresse/);
  expect(verification.html).toBe("");
  await page.goto(linkOf(verification.text));
  await expect(page.getByTestId("verified-ok")).toBeVisible();
  await expect(page.getByTestId("header-account")).toBeVisible();

  await screens(page, baseURL, "/fr/account", "account-page", "[data-testid=account-email]");
  await page.goto(site(baseURL, "/fr/account"));
  await expect(page.getByTestId("account-email")).toHaveText(email);
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByTestId("header-sign-in")).toBeVisible();

  await signIn(page, baseURL, email, "a wrong password, long");
  await expect(page.getByText("E-mail ou mot de passe incorrect.")).toBeVisible({ timeout: 30_000 });
  await signIn(page, baseURL, email, PASSWORD);
  await expect(page.getByTestId("account-email")).toHaveText(email, { timeout: 30_000 });
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByTestId("header-sign-in")).toBeVisible();

  await page.goto(site(baseURL, "/fr/account/forgot-password"));
  await page.getByLabel("Adresse e-mail").fill(`nobody-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "ENVOYER LE LIEN" }).click();
  await expect(page.getByTestId("forgot-done")).toBeVisible({ timeout: 30_000 });
  await page.goto(site(baseURL, "/fr/account/forgot-password"));
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByRole("button", { name: "ENVOYER LE LIEN" }).click();
  await expect(page.getByTestId("forgot-done")).toBeVisible({ timeout: 30_000 });
  const reset = await waitForMail(request, email, /nouveau mot de passe/);
  expect(reset.html).toBe("");
  await page.goto(linkOf(reset.text));
  await expect(page).toHaveURL(/\/fr\/account\/new-password\?token=/);
  await page.getByLabel("Nouveau mot de passe").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "ENREGISTRER LE MOT DE PASSE" }).click();
  await expect(page.getByTestId("new-password-done")).toBeVisible();

  await signIn(page, baseURL, email, NEW_PASSWORD);
  await expect(page.getByTestId("account-email")).toHaveText(email, { timeout: 30_000 });
  await page.getByRole("button", { name: "SUPPRIMER MON COMPTE" }).click();
  await page.getByLabel("Mot de passe", { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "OUI, SUPPRIMER POUR DE BON" }).click();
  await expect(page.getByTestId("account-deleted")).toBeVisible();

  await page.waitForTimeout(SIGN_IN_WINDOW_MS);
  await signIn(page, baseURL, email, NEW_PASSWORD);
  await expect(page.getByText("E-mail ou mot de passe incorrect.")).toBeVisible({ timeout: 30_000 });
});

test("the website relays /api only: the guard of the counter is out of reach", async ({ request, baseURL }) => {
  expect((await request.post(site(baseURL, "/internal/auth-guard"))).status()).toBe(404);
  const relayed = await request.post(site(baseURL, "/api/internal/auth-guard"), { data: { action: "sign_in" } });
  expect(relayed.status()).toBe(404);
  const session = await request.get(site(baseURL, "/api/auth/get-session"));
  expect(session.status()).toBe(200);
});

test("the ALTCHA proof stays under one second on a slowed down processor", async ({ page, baseURL }) => {
  await page.goto(site(baseURL, "/en/account/sign-in"));
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: MID_PHONE_SLOWDOWN });
  const times = await page.evaluate(async (runs) => {
    await customElements.whenDefined("altcha-widget");
    const widget = document.querySelector("altcha-widget") as HTMLElement & {
      reset: () => void;
      verify: (options?: { minDuration?: number }) => Promise<{ payload: string } | null>;
    };
    while (typeof widget.verify !== "function") {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const measured: number[] = [];
    for (let index = 0; index < runs; index += 1) {
      widget.reset();
      const start = performance.now();
      const result = await widget.verify({ minDuration: 0 });
      if (result === null) {
        throw new Error("the widget did not solve the challenge");
      }
      measured.push(performance.now() - start);
    }
    return measured;
  }, ALTCHA_RUNS);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  const sorted = [...times].sort((first, second) => first - second);
  const median = sorted[Math.floor(sorted.length / 2)] ?? 0;
  mkdirSync(RESULTS, { recursive: true });
  writeFileSync(join(RESULTS, "altcha-timing.json"), JSON.stringify({ slowdown: MID_PHONE_SLOWDOWN, times, median }, null, 2));
  expect(median).toBeLessThan(1000);
});
