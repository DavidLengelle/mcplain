import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "./test";

import { fulfill, ID, serveAnalysis } from "./fake-api";
import { reportView } from "./reports";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");

type Sent = { body: unknown; altcha: string | undefined; origin: string | undefined };

test("a visitor reports a missed danger from a report, with ALTCHA and a comment, and is thanked", async ({ page }) => {
  const sent: Sent[] = [];
  await serveAnalysis(page, [reportView("orange")]);
  await page.route(`**/api/analyses/${ID}/reports`, async (route) => {
    const request = route.request();
    const headers = request.headers();
    sent.push({ body: JSON.parse(request.postData() ?? "null"), altcha: headers["x-altcha"], origin: headers.origin });
    await fulfill(route, 201, { ok: true });
  });
  await page.goto(`/fr/analyses/${ID}`);
  const box = page.locator("[data-report-box]");
  await expect(box).toBeVisible();
  await box.getByRole("button", { name: "Signaler" }).click();
  await box.getByRole("radio", { name: /Danger non détecté/ }).check();
  await box.getByLabel("Commentaire (facultatif)").fill("Il lit le fichier ~/.ssh/config.");
  await expect(box.locator("[data-report-count]")).toHaveText("468 caractères restants");
  await box.getByRole("button", { name: "Envoyer" }).click();
  await expect(box.locator("[data-report-thanks]")).toContainText("Merci !");
  expect(sent).toHaveLength(1);
  expect(sent[0]?.body).toEqual({ kind: "missed_danger", comment: "Il lit le fichier ~/.ssh/config." });
  expect(sent[0]?.altcha).toBeTruthy();
  expect(sent[0]?.origin).toBe(new URL(page.url()).origin);
});

test("a full box says to try again tomorrow, and the form stays", async ({ page }) => {
  await serveAnalysis(page, [reportView("green")]);
  await page.route(`**/api/analyses/${ID}/reports`, async (route) => {
    await fulfill(route, 429, { error: { code: "report_global", params: { resets_at: "2026-12-02T00:00:00+00:00" } } });
  });
  await page.goto(`/analyses/${ID}`);
  const box = page.locator("[data-report-box]");
  await box.getByRole("button", { name: "Report" }).click();
  await box.getByRole("radio", { name: /Are you the author/ }).check();
  await box.getByRole("button", { name: "Send" }).click();
  await expect(box.getByText("The box is full, try again tomorrow.")).toBeVisible();
  await expect(box.getByRole("button", { name: "Send" })).toBeEnabled();
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 390] as const) {
    test(`screenshot of the open report box, ${theme} theme, ${width} px, without sideways scroll`, async ({ page }) => {
      mkdirSync(SCREENS, { recursive: true });
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await serveAnalysis(page, [reportView("red")]);
      await page.goto(`/fr/analyses/${ID}`);
      const box = page.locator("[data-report-box]");
      await box.getByRole("button", { name: "Signaler" }).click();
      await box.getByRole("radio", { name: /Tu es l'auteur/ }).check();
      await box.getByLabel("Commentaire (facultatif)").fill("Le rapport se trompe sur l'outil fetch_url.");
      await box.scrollIntoViewIfNeeded();
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scroll).toBeLessThanOrEqual(width);
      await box.screenshot({ path: join(SCREENS, `report-box-${theme}-${width}.png`) });
    });
  }
}
