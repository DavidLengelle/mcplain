import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { cleanUp, linkOf, RESULTS, screens, signIn, site, waitForMail } from "./helpers";

const PASSWORD = "first password, long enough";
const NEW_PASSWORD = "second password, long enough";
const ALTCHA_RUNS = 10;
const MID_PHONE_SLOWDOWN = 4;
const SIGN_IN_WINDOW_MS = 11_000;
const addresses: string[] = [];

test.afterEach(async ({ request }) => {
  await cleanUp(request, addresses.splice(0));
});

test("an account is created, verified, used, recovered and deleted", async ({ page, request, baseURL }) => {
  const email = `ada-${Date.now()}@example.com`;
  const nobody = `nobody-${Date.now()}@example.com`;
  addresses.push(email, nobody);

  await screens(page, baseURL, "/fr/account/sign-up", "account-sign-up", "form");
  await page.goto(site(baseURL, "/fr/account/sign-up"));
  await expect(page.getByTestId("header-sign-in")).toBeVisible();
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "CRÉER MON COMPTE" }).click();
  await expect(page.getByTestId("sign-up-done")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("ALTCHA").filter({ visible: true })).toHaveCount(0);

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
  await page.getByLabel("Adresse e-mail").fill(nobody);
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
  const maximum = sorted[sorted.length - 1] ?? 0;
  const challenge = (await (await page.request.get(site(baseURL, "/api/altcha/challenge"))).json()) as { parameters: { cost: number } };
  const cost = challenge.parameters.cost;
  mkdirSync(RESULTS, { recursive: true });
  writeFileSync(
    join(RESULTS, "altcha-timing.json"),
    JSON.stringify({ cost, slowdown: MID_PHONE_SLOWDOWN, times, median, maximum }, null, 2),
  );
  expect(cost).toBe(5000);
  expect(median).toBeLessThan(1000);
});
