import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { fulfill, ID, serveAnalysis } from "./fake-api";
import { reportView } from "./reports";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");
const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;
const FALLBACK = {
  variant: "tools",
  messages: [
    { code: "ai.notice.fallback.count", params: { count: "14" } },
    { code: "ai.notice.fallback.can", params: {} },
    { code: "ai.notice.fallback.unavailable", params: {} },
  ],
  actions: ["lamp.files_read.phrase", "lamp.files_write.phrase"],
};
const CONTENT = {
  summary: "Ce serveur sert à lire et ranger les fichiers de ton ordinateur.",
  use_cases: ["Chercher un fichier.", "Ranger un dossier."],
  tool_titles: [{ tool_index: 0, title: "Lire un fichier", sentence: "Il lit le contenu d'un fichier." }],
  alert: null as string | null,
};

type Json = Record<string, unknown>;

function answer(status: string, extra: Json = {}): Json {
  return {
    id: ID,
    kind: "notice",
    lang: "fr",
    status,
    source: "template",
    fallback: FALLBACK,
    content: null,
    model: null,
    date: null,
    reject_reason: null,
    resume: null,
    ...extra,
  };
}

function ready(alert: string | null = null): Json {
  return answer("ready", { source: "ai", content: { ...CONTENT, alert }, model: "some-model", date: "2026-11-09T10:00:00+00:00" });
}

async function serveText(page: Page, kind: string, answers: Json[]): Promise<void> {
  let index = 0;
  await page.route(new RegExp(`/api/analyses/${ID}/${kind}(\\?.*)?$`), async (route) => {
    const body = answers[Math.min(index, answers.length - 1)];
    index += 1;
    await fulfill(route, 200, body);
  });
}

async function open(page: Page, notice: Json[], translation: Json[] = [answer("template", { fallback: null })]): Promise<void> {
  await serveAnalysis(page, [reportView("orange")]);
  await serveText(page, "notice", notice);
  await serveText(page, "translation", translation);
  await page.goto(`/fr/analyses/${ID}`);
}

test("a ready notice with its mark, and the titles in the grid", async ({ page }) => {
  await open(page, [ready()]);
  await expect(page.locator("[data-notice-ai]")).toContainText(CONTENT.summary);
  await expect(page.locator("[data-notice-ai]")).toContainText("Résumé automatique");
  await expect(page.locator("[data-notice-ai]")).toContainText("ne change jamais le verdict");
  await expect(page.locator('[data-tool-card="0"]')).toContainText("Lire un fichier");
  await expect(page.locator('[data-tool-card="0"]')).toContainText("Résumé automatique");
  await expect(page.locator("[data-ai-alert]")).toHaveCount(0);
  await expect(page.locator('[data-verdict-word="orange"]')).toBeVisible();
});

test("a waiting notice, then ready", async ({ page }) => {
  await open(page, [answer("pending"), answer("pending"), ready()]);
  await expect(page.locator("[data-notice-pending]")).toBeVisible();
  await expect(page.locator("[data-notice-fallback]")).toBeVisible();
  await expect(page.locator("[data-notice-ai]")).toBeVisible({ timeout: 8000 });
  await expect(page.locator("[data-notice-pending]")).toHaveCount(0);
});

test("a notice that waits too long keeps the fallback", async ({ page }) => {
  await page.clock.install();
  await open(page, [answer("pending")]);
  await expect(page.locator("[data-notice-pending]")).toBeVisible();
  for (let step = 0; step < 17; step += 1) {
    await page.clock.runFor(2000);
  }
  await expect(page.locator("[data-notice-pending]")).toHaveCount(0);
  await expect(page.locator("[data-notice-fallback]")).toContainText("MCPlain n'a pas pu écrire de résumé automatique");
});

test("a rejected notice shows the fallback only", async ({ page }) => {
  await open(page, [answer("rejected", { reject_reason: "forbidden_word" })]);
  await expect(page.locator("[data-notice-fallback]")).toContainText("Il peut lire tes fichiers et modifier tes fichiers");
  await expect(page.locator("[data-notice-ai]")).toHaveCount(0);
  await expect(page.locator('[data-tool-card="0"]')).not.toContainText("Résumé automatique");
});

for (const [resume, sentence] of [
  ["tomorrow", "La notice automatique revient demain."],
  ["next_month", "La notice automatique revient le mois prochain."],
] as const) {
  test(`a paused notice says it comes back: ${resume}`, async ({ page }) => {
    await open(page, [answer("paused", { resume, reject_reason: "daily_fuse" })]);
    await expect(page.locator(`[data-notice-resume="${resume}"]`)).toHaveText(sentence);
    await expect(page.locator("[data-notice-fallback]")).toBeVisible();
  });
}

test("the opinion of the AI stays out of the gauge and the lamps", async ({ page }) => {
  await open(page, [ready("Un outil de météo qui touche à tes secrets, c'est étonnant.")]);
  const alert = page.locator("[data-ai-alert]");
  await expect(alert).toContainText("Avis de l'IA");
  await expect(alert).toContainText("c'est étonnant");
  await expect(page.locator("[data-verdict] [data-ai-alert]")).toHaveCount(0);
  await expect(page.locator("[data-lamp] [data-ai-alert]")).toHaveCount(0);
  await expect(page.locator('[data-verdict-word="orange"]')).toBeVisible();
});

test("the translation shows with its mark, and a rejected one keeps the original", async ({ page }) => {
  const translated = answer("ready", {
    kind: "translation",
    fallback: null,
    source: "ai",
    content: { items: Array.from({ length: 20 }, (_, index) => ({ id: `tool_${index}`, text: "Lit un fichier de ton ordinateur." })) },
  });
  await open(page, [answer("failed")], [translated]);
  await expect(page.locator('[data-translated="true"]')).toHaveText("Traduction automatique du texte de l'auteur, pas un avis de MCPlain");
  await expect(page.locator("[data-description]")).toContainText("Lit un fichier de ton ordinateur.");
  await page.getByRole("button", { name: "Voir l'original" }).click();
  await expect(page.locator('[data-translated="false"]')).toHaveText("Texte de l'auteur");
});

test("the parameters are translated too, and the whole card switches back to the original", async ({ page }) => {
  const translated = answer("ready", {
    kind: "translation",
    fallback: null,
    source: "ai",
    content: {
      items: [
        { id: "tool_0", text: "Lit tout le contenu d'un fichier." },
        { id: "tool_0_param_1", text: "Si présent, ne renvoie que les N dernières lignes." },
      ],
    },
  });
  await open(page, [answer("failed")], [translated]);
  await page.locator('[data-tool-card="0"]').click();
  const card = page.locator("[data-announced]");
  await expect(card.locator('[data-translated="true"]')).toHaveText("Traduction automatique du texte de l'auteur, pas un avis de MCPlain");
  await expect(card.locator('[data-parameter="1"]')).toContainText("Si présent, ne renvoie que les N dernières lignes.");
  await expect(card.locator('[data-parameter="2"]')).toHaveAttribute("data-parameter-translated", "false");
  await expect(card.locator('[data-parameter="2"]')).toContainText("If provided");
  await card.getByRole("button", { name: "Voir l'original" }).click();
  await expect(card.locator("[data-description]")).toContainText("Read the complete contents");
  await expect(card.locator('[data-parameter="1"]')).toContainText("If provided");
  await card.getByRole("button", { name: "Voir la traduction" }).click();
  await expect(card.locator('[data-parameter="1"]')).toContainText("Si présent");
});

test("a rejected translation keeps the text of the author", async ({ page }) => {
  await open(page, [answer("failed")], [answer("rejected", { kind: "translation", fallback: null, reject_reason: "link" })]);
  await expect(page.locator("[data-description]")).toBeVisible();
  await expect(page.locator("[data-translated]")).toHaveCount(0);
  await expect(page.getByText("Texte de l'auteur").first()).toBeVisible();
});

test("the English page never asks for a translation", async ({ page }) => {
  const asked: string[] = [];
  await serveAnalysis(page, [reportView("orange")]);
  await serveText(page, "notice", [ready()]);
  await page.route(new RegExp(`/api/analyses/${ID}/translation`), async (route) => {
    asked.push(route.request().url());
    await fulfill(route, 200, answer("template"));
  });
  await page.goto(`/en/analyses/${ID}`);
  await expect(page.locator("[data-notice-ai]")).toBeVisible();
  expect(asked).toEqual([]);
});

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`screenshot of the notice, ${theme} theme, ${width} px`, async ({ page }) => {
      mkdirSync(SCREENS, { recursive: true });
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await open(page, [ready("Un outil de météo qui touche à tes secrets, c'est étonnant.")]);
      await expect(page.locator("[data-ai-alert]")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow).toBe(false);
      await page.locator("[data-notice]").screenshot({ path: join(SCREENS, `notice-${theme}-${width}.png`) });
      await page.screenshot({ path: join(SCREENS, `notice-page-${theme}-${width}.png`), fullPage: true });
    });
  }
}

for (const width of WIDTHS) {
  test(`screenshot of the fallback, ${width} px`, async ({ page }) => {
    mkdirSync(SCREENS, { recursive: true });
    await page.setViewportSize({ width, height: 900 });
    await open(page, [answer("paused", { resume: "tomorrow" })]);
    await expect(page.locator("[data-notice-resume]")).toBeVisible();
    await page.locator("[data-notice]").screenshot({ path: join(SCREENS, `notice-fallback-${width}.png`) });
  });
}
