import { mkdirSync } from "node:fs";
import { join } from "node:path";

import type { Page } from "@playwright/test";

import { expect, test } from "./test";

import { fulfill } from "./fake-api";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");
const ANALYSIS = "11111111-1111-4111-8111-111111111111";
const TEXT = "22222222-2222-4222-8222-222222222222";
const ENTRY = "44444444-4444-4444-8444-444444444444";
const ADMIN = { id: "a1", email: "boss@example.com", name: "", emailVerified: true, role: "admin", twoFactorEnabled: true, createdAt: "2026-11-01T00:00:00.000Z", updatedAt: "2026-11-01T00:00:00.000Z" };
const SESSION = { id: "s1", userId: "a1", token: "t", expiresAt: "2099-01-01T00:00:00.000Z", createdAt: "2026-11-01T00:00:00.000Z", updatedAt: "2026-11-01T00:00:00.000Z" };

function days(count: number, make: (index: number) => Record<string, unknown>): Record<string, unknown>[] {
  const items: Record<string, unknown>[] = [];
  for (let index = count - 1; index >= 0; index -= 1) {
    items.push({ day: new Date(Date.UTC(2026, 11, 1) - index * 86_400_000).toISOString().slice(0, 10), ...make(index) });
  }
  return items;
}

type Seen = { method: string; url: string; body: string | null };

async function serveDashboard(page: Page, retry: { status: number; body: unknown } = { status: 202, body: { id: TEXT, status: "pending" } }): Promise<Seen[]> {
  const seen: Seen[] = [];
  let entries: Record<string, unknown>[] = [];
  let balance: number | null = null;
  await page.route("**/api/auth/get-session", async (route) => {
    await fulfill(route, 200, { session: SESSION, user: ADMIN });
  });
  await page.route("**/api/admin/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    seen.push({ method: request.method(), url: url.pathname + url.search, body: request.postData() });
    const count = Number(url.searchParams.get("days") ?? "30");
    const path = url.pathname;
    if (path === "/api/admin/dashboard/spend") {
      await fulfill(route, 200, {
        days: count,
        today_usd: 0.4,
        month_usd: 3.2,
        daily_fuse_usd: 0.5,
        monthly_budget_usd: 10,
        fuse_reached: false,
        budget_reached: false,
        per_day: days(count, (index) => ({ cost_usd: (index % 5) * 0.05, notice_usd: 0.03, translation_usd: 0.02, paid_calls: index % 4 })),
        by_kind: { notice: 2.1, translation: 1.1 },
        paid_calls: 41,
        writer: { disabled_reason: null, paused_until: null },
      });
      return;
    }
    if (path === "/api/admin/dashboard/ai") {
      await fulfill(route, 200, {
        days: count,
        per_day: days(count, (index) => ({ reasons: { encoding: index % 2 } })),
        reasons: { encoding: 6, link: 1 },
        encoding: { rejected: 6, paid_notice_calls: 40, rate: 0.15 },
        alerts: [{ id: "33333333-3333-4333-8333-333333333333", code: "usage_limit", created_at: "2026-12-01T08:00:00+00:00", kind: "notice", status: 400, emailed_at: "2026-12-01T08:00:05+00:00", read_at: null }],
        texts: [{ id: TEXT, kind: "notice", lang: "fr", status: "rejected", reject_reason: "link", updated_at: "2026-12-01T07:00:00+00:00", analysis_id: ANALYSIS }],
        writer: { disabled_reason: null, paused_until: null },
      });
      return;
    }
    if (path === "/api/admin/dashboard/analyses") {
      await fulfill(route, 200, {
        days: count,
        per_day: days(count, (index) => ({ total: 10 + index, cached: 4, new: 6 + index })),
        colors: { red: 1, orange: 34, gray: 12, green: 5 },
        gray_cases: [{ code: "no_tools_found", count: 7 }, { code: "incomplete_tracking", count: 5 }],
        languages: [{ code: "go", count: 3 }, { code: "rust", count: 1 }],
        failures: [{ code: "fetch.npm_not_found", count: 4, refund: "keep" }, { code: "atelier_timeout", count: 1, refund: "give_back" }],
        top: [
          { kind: "pypi", name: "mcp-server-fetch", count: 21, last_analysis_id: ANALYSIS },
          { kind: "npm", name: "@modelcontextprotocol/server-filesystem-with-a-very-long-name-for-phones", count: 9, last_analysis_id: ANALYSIS },
        ],
      });
      return;
    }
    if (path === "/api/admin/dashboard/refusals") {
      await fulfill(route, 200, {
        days: count,
        kinds: ["signup_limit", "quota_exhausted_anonymous", "quota_exhausted_account"],
        per_day: days(count, (index) => ({ counts: { signup_limit: index % 2, quota_exhausted_anonymous: index % 3, quota_exhausted_account: 0 } })),
        totals: { signup_limit: 15, quota_exhausted_anonymous: 20, quota_exhausted_account: 0 },
      });
      return;
    }
    if (path === "/api/admin/dashboard/accounts") {
      await fulfill(route, 200, { days: count, per_day: days(count, (index) => ({ count: index % 3 })), total: count });
      return;
    }
    if (path === "/api/admin/credit" && request.method() === "POST") {
      const sent = JSON.parse(request.postData() ?? "{}") as { kind: string; amount_usd: number; note: string | null };
      balance = sent.amount_usd;
      entries = [{ id: ENTRY, kind: sent.kind, amount_usd: sent.amount_usd, note: sent.note, created_at: "2026-12-01T09:00:00+00:00" }];
    }
    if (path === "/api/admin/credit") {
      let statementAt: string | null = null;
      let last: string | null = null;
      let status = 200;
      if (request.method() === "POST") {
        status = 201;
      }
      if (balance !== null) {
        statementAt = "2026-12-01T09:00:00+00:00";
        last = ENTRY;
      }
      await fulfill(route, status, {
        balance_usd: balance,
        statement_usd: balance,
        statement_at: statementAt,
        top_ups_usd: 0,
        spent_usd: 0,
        threshold_usd: 2,
        low: false,
        alert_sent_at: null,
        last_entry_id: last,
        entries,
      });
      return;
    }
    if (path.startsWith("/api/admin/texts/")) {
      await fulfill(route, retry.status, retry.body);
      return;
    }
    if (path === "/api/admin/journal") {
      await fulfill(route, 200, { lines: [{ id: "j1", action: "ban", target_kind: "account", target_id: "someone", created_at: "2026-12-01T09:00:00+00:00" }] });
      return;
    }
    await fulfill(route, 404, { error: { code: "api.not_found", params: {} } });
  });
  return seen;
}

test("the admin sees every dial over 30 days, then 7 days after the switch", async ({ page }) => {
  const seen = await serveDashboard(page);
  await page.goto("/fr/admin");
  await expect(page.getByTestId("admin-spend-today")).toContainText("sur");
  await expect(page.getByTestId("admin-spend-days").getByRole("listitem")).toHaveCount(30);
  await expect(page.getByTestId("admin-top")).toContainText("mcp-server-fetch");
  await expect(page.getByTestId("admin-encoding-rate")).toContainText("15");
  await expect(page.getByRole("heading", { name: "Comptes", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "7 j" }).click();
  await expect(page.getByTestId("admin-spend-days").getByRole("listitem")).toHaveCount(7);
  await expect(page.getByTestId("admin-analyses-days").getByRole("listitem")).toHaveCount(7);
  expect(seen.some((item) => item.url === "/api/admin/dashboard/analyses?days=7")).toBe(true);
});

test("the admin adds a first statement read in the Anthropic console", async ({ page }) => {
  const seen = await serveDashboard(page);
  await page.goto("/fr/admin");
  await expect(page.getByTestId("admin-balance-empty")).toHaveText("Saisis un premier relevé (solde lu dans la console Anthropic).");
  await page.getByLabel("Montant en dollars").fill("9,75");
  await page.getByRole("button", { name: "AJOUTER" }).click();
  await expect(page.getByTestId("admin-balance-amount")).toContainText("9,75");
  const posted = seen.find((item) => item.method === "POST" && item.url === "/api/admin/credit");
  expect(JSON.parse(posted?.body ?? "{}")).toEqual({ kind: "statement", amount_usd: 9.75, note: null });
});

test("the admin asks a rejected notice again after a confirmation, and a fuse is said plainly", async ({ page }) => {
  const seen = await serveDashboard(page, { status: 409, body: { error: { code: "api.daily_text_cap", params: {} } } });
  await page.goto("/fr/admin");
  const texts = page.getByTestId("admin-texts");
  await texts.getByRole("button", { name: "Relancer la notice" }).click();
  await texts.getByRole("button", { name: "Oui, relancer" }).click();
  await expect(page.getByText("Bloqué : cette notice a déjà été demandée 4 fois aujourd'hui. Réessaie demain.")).toBeVisible();
  expect(seen.filter((item) => item.url === `/api/admin/texts/${TEXT}/retry`)).toHaveLength(1);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 390] as const) {
    test(`screenshot of the admin dashboard, ${theme} theme, ${width} px, without sideways scroll`, async ({ page }) => {
      mkdirSync(SCREENS, { recursive: true });
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await serveDashboard(page);
      await page.goto("/fr/admin");
      await expect(page.getByTestId("admin-top")).toBeVisible();
      await expect(page.getByTestId("admin-journal")).toBeVisible();
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scroll).toBeLessThanOrEqual(width);
      await page.screenshot({ path: join(SCREENS, `admin-${theme}-${width}.png`), fullPage: true });
    });
  }
}
