import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/components/admin/dashboard";
import { parseAmount, parseCredit, parseSpend, share } from "@/lib/admin-dashboard";

import { renderWithIntl } from "./intl";

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

const ANALYSIS = "11111111-1111-4111-8111-111111111111";
const TEXT = "22222222-2222-4222-8222-222222222222";
const ALERT = "33333333-3333-4333-8333-333333333333";
const ENTRY = "44444444-4444-4444-8444-444444444444";
const TRAPPED_NAME = "@evil/pkg‮<b>x</b>";

function days(count: number, make: (day: string) => Record<string, unknown>): Record<string, unknown>[] {
  const items: Record<string, unknown>[] = [];
  for (let index = count - 1; index >= 0; index -= 1) {
    const day = new Date(Date.UTC(2026, 11, 1) - index * 86_400_000).toISOString().slice(0, 10);
    items.push({ day, ...make(day) });
  }
  return items;
}

function spend(count: number, fuseReached = false) {
  return {
    days: count,
    today_usd: 0.03,
    month_usd: 1.25,
    daily_fuse_usd: 0.5,
    monthly_budget_usd: 10,
    fuse_reached: fuseReached,
    budget_reached: false,
    per_day: days(count, (day) => ({ cost_usd: costOf(day), notice_usd: 0.01, translation_usd: 0.02, paid_calls: 2 })),
    by_kind: { notice: 0.01, translation: 0.02 },
    paid_calls: 2,
    writer: { disabled_reason: null, paused_until: null },
  };
}

function ai(count: number) {
  return {
    days: count,
    per_day: days(count, () => ({ reasons: { encoding: 1 } })),
    reasons: { encoding: count, link: 1 },
    encoding: { rejected: 1, paid_notice_calls: 4, rate: 0.25 },
    alerts: [{ id: ALERT, code: "usage_limit", created_at: "2026-12-01T08:00:00+00:00", kind: "notice", status: 400, emailed_at: null, read_at: null }],
    texts: [
      { id: TEXT, kind: "notice", lang: "fr", status: "rejected", reject_reason: "link", updated_at: "2026-12-01T07:00:00+00:00", analysis_id: ANALYSIS },
      { id: "t2", kind: "translation", lang: "fr", status: "paused", reject_reason: "daily_fuse", updated_at: "2026-12-01T06:00:00+00:00", analysis_id: null },
    ],
    writer: { disabled_reason: null, paused_until: null },
  };
}

function analyses(count: number) {
  return {
    days: count,
    per_day: days(count, () => ({ total: 3, cached: 1, new: 2 })),
    colors: { red: 1, orange: 2, gray: 3, green: 4 },
    gray_cases: [{ code: "no_tools_found", count: 3 }],
    languages: [{ code: "go", count: 2 }],
    failures: [
      { code: "atelier_timeout", count: 1, refund: "give_back" },
      { code: "fetch.npm_not_found", count: 2, refund: "keep" },
    ],
    top: [{ kind: "npm", name: TRAPPED_NAME, count: 5, last_analysis_id: ANALYSIS }],
  };
}

function refusals(count: number) {
  return {
    days: count,
    kinds: ["signup_limit", "quota_exhausted_anonymous", "quota_exhausted_account"],
    per_day: days(count, () => ({ counts: { signup_limit: 1, quota_exhausted_anonymous: 0, quota_exhausted_account: 2 } })),
    totals: { signup_limit: count, quota_exhausted_anonymous: 0, quota_exhausted_account: 2 * count },
  };
}

function credit(balance: number | null, low = false) {
  let entries: unknown[] = [];
  let statementAt: string | null = null;
  let lastEntry: string | null = null;
  if (balance !== null) {
    statementAt = "2026-12-01T08:00:00+00:00";
    lastEntry = ENTRY;
    entries = [{ id: ENTRY, kind: "statement", amount_usd: balance, note: "lu ‮ <i>console</i>", created_at: "2026-12-01T08:00:00+00:00" }];
  }
  return {
    balance_usd: balance,
    statement_usd: balance,
    statement_at: statementAt,
    top_ups_usd: 0,
    spent_usd: 0,
    threshold_usd: 2,
    low,
    alert_sent_at: null,
    last_entry_id: lastEntry,
    entries,
  };
}

function plain(value: string | null | undefined): string {
  return (value ?? "").replace(/\s/g, " ");
}

function costOf(day: string): number {
  if (day === "2026-12-01") {
    return 0.03;
  }
  return 0;
}

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Call = { url: string; method: string; body: unknown };

function fakeApi(options: { balance?: number | null; low?: boolean; retry?: { status: number; body: unknown }; accountsDown?: boolean } = {}) {
  const calls: Call[] = [];
  let balance = options.balance ?? null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      let body: unknown = null;
      if (typeof init?.body === "string") {
        body = JSON.parse(init.body);
      }
      calls.push({ url, method, body });
      const count = Number(new URL(url, "http://localhost").searchParams.get("days") ?? "30");
      if (url.startsWith("/api/admin/dashboard/spend")) {
        return answer(200, spend(count));
      }
      if (url.startsWith("/api/admin/dashboard/ai")) {
        return answer(200, ai(count));
      }
      if (url.startsWith("/api/admin/dashboard/analyses")) {
        return answer(200, analyses(count));
      }
      if (url.startsWith("/api/admin/dashboard/refusals")) {
        return answer(200, refusals(count));
      }
      if (url.startsWith("/api/admin/dashboard/accounts")) {
        if (options.accountsDown) {
          return answer(503, { error: { code: "api.guichet_unavailable", params: {} } });
        }
        return answer(200, { days: count, per_day: days(count, () => ({ count: 1 })), total: count });
      }
      if (url === "/api/admin/credit" && method === "POST") {
        balance = (body as { amount_usd: number }).amount_usd;
        return answer(201, credit(balance));
      }
      if (url === "/api/admin/credit") {
        return answer(200, credit(balance, options.low ?? false));
      }
      if (url.startsWith("/api/admin/texts/") && options.retry !== undefined) {
        return answer(options.retry.status, options.retry.body);
      }
      if (url === "/api/admin/journal") {
        return answer(200, { lines: [{ id: "j1", action: "analysis_rerun", target_kind: "analysis", target_id: ANALYSIS, created_at: "2026-12-01T09:00:00+00:00" }] });
      }
      return answer(202, { ok: true });
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the admin dashboard", () => {
  it("shows the dials in the asked order, over 30 days by default, with a number next to every bar", async () => {
    const calls = fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    await screen.findByTestId("admin-spend-today");
    const titles = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(titles).toEqual([
      "Dépense de l'IA",
      "Solde estimé du crédit Anthropic",
      "Alertes de l'IA",
      "Rejets de l'IA",
      "Notices à relancer",
      "Échecs d'analyse",
      "Analyses par jour",
      "Couleurs des verdicts",
      "MCP les plus analysés",
      "Langages non pris en charge demandés",
      "Refus",
      "Fréquentation : comptes créés",
      "Journal admin",
    ]);
    expect(calls.filter((call) => call.url.startsWith("/api/admin/dashboard/")).every((call) => call.url.endsWith("days=30"))).toBe(true);
    expect(plain(screen.getByTestId("admin-spend-today").textContent)).toContain("0,03 $US sur 0,50 $US");
    await waitFor(() => expect(within(screen.getByTestId("admin-spend-days")).getAllByRole("listitem")).toHaveLength(30));
    for (const bar of document.querySelectorAll("progress")) {
      expect(bar.getAttribute("aria-label")).toMatch(/ : |\d/);
      expect(bar.parentElement?.textContent?.trim()).not.toBe("");
    }
    expect(plain((await screen.findByTestId("admin-encoding-rate")).textContent)).toBe("Taux de rejets « encoding » : 25 % (1 sur 4 appels de notice payés)");
    expect(screen.getByTestId("admin-failures").textContent).toContain("Jeton gardé (faute du lien)");
    expect(screen.getByTestId("admin-failures").textContent).toContain("Jeton rendu (faute de MCPlain)");
  });

  it("asks every dial again for 7 days, and again on Refresh", async () => {
    const calls = fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    await screen.findByTestId("admin-spend-today");
    fireEvent.click(screen.getByRole("button", { name: "7 j" }));
    await waitFor(() => expect(within(screen.getByTestId("admin-spend-days")).getAllByRole("listitem")).toHaveLength(7));
    expect(screen.getByRole("button", { name: "7 j" }).getAttribute("aria-pressed")).toBe("true");
    for (const name of ["spend", "ai", "analyses", "refusals", "accounts"]) {
      expect(calls.some((call) => call.url === `/api/admin/dashboard/${name}?days=7`)).toBe(true);
    }
    const before = calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Actualiser" }));
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(before + 7));
  });

  it("asks for a first statement, then adds it as a number in dollars", async () => {
    const calls = fakeApi({ balance: null });
    renderWithIntl(<Dashboard />, "fr");
    expect((await screen.findByTestId("admin-balance-empty")).textContent).toBe("Saisis un premier relevé (solde lu dans la console Anthropic).");
    fireEvent.change(screen.getByLabelText("Montant en dollars"), { target: { value: "9,75" } });
    fireEvent.change(screen.getByLabelText("Note (facultative)"), { target: { value: "  lu le 1er  " } });
    fireEvent.click(screen.getByRole("button", { name: "AJOUTER" }));
    await waitFor(() => expect(calls.some((call) => call.method === "POST" && call.url === "/api/admin/credit")).toBe(true));
    const posted = calls.find((call) => call.method === "POST" && call.url === "/api/admin/credit");
    expect(posted?.body).toEqual({ kind: "statement", amount_usd: 9.75, note: "lu le 1er" });
    expect((await screen.findByTestId("admin-balance-amount")).textContent).toContain("9,75");
    expect(screen.getByText("Estimation : le vrai solde est dans la console Anthropic.")).toBeTruthy();
  });

  it("refuses a typed amount that is not a number, without calling the API", async () => {
    const calls = fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    await screen.findByTestId("admin-balance-empty");
    fireEvent.change(screen.getByLabelText("Montant en dollars"), { target: { value: "dix" } });
    fireEvent.click(screen.getByRole("button", { name: "AJOUTER" }));
    expect(await screen.findByText("Écris un montant en dollars, par exemple 9,75.")).toBeTruthy();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  it("shows a low balance with its word, and the note of an entry as raw text", async () => {
    fakeApi({ balance: 1.5, low: true });
    renderWithIntl(<Dashboard />, "fr");
    expect(plain((await screen.findByTestId("admin-balance-low")).textContent)).toBe("Sous le seuil de 2,00 $US.");
    const entries = screen.getByTestId("admin-credit-entries");
    expect(entries.querySelector("i")).toBeNull();
    expect(entries.textContent).not.toContain("‮");
    expect(screen.getByTestId("admin-credit-delete")).toBeTruthy();
  });

  it("asks the notice again only after a confirmation, and says plainly when a fuse blocks", async () => {
    const calls = fakeApi({ retry: { status: 409, body: { error: { code: "api.daily_fuse", params: { detail: "2026-12-02T00:00:00+00:00" } } } } });
    renderWithIntl(<Dashboard />, "fr");
    const texts = await screen.findByTestId("admin-texts");
    expect(within(texts).getAllByTestId("admin-text-retry")).toHaveLength(1);
    fireEvent.click(within(texts).getByTestId("admin-text-retry"));
    expect(calls.some((call) => call.url.startsWith("/api/admin/texts/"))).toBe(false);
    fireEvent.click(within(texts).getByRole("button", { name: "Oui, relancer" }));
    await waitFor(() => expect(calls.some((call) => call.url === `/api/admin/texts/${TEXT}/retry` && call.method === "POST")).toBe(true));
    expect(await screen.findByText("Bloqué : le budget IA du jour est épuisé. Il revient demain.")).toBeTruthy();
  });

  it("can cancel a rerun of an analysis, then sends it", async () => {
    const calls = fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    const top = await screen.findByTestId("admin-top");
    fireEvent.click(within(top).getByTestId("admin-analysis-rerun"));
    fireEvent.click(within(top).getByRole("button", { name: "Annuler" }));
    expect(calls.some((call) => call.url.endsWith("/rerun"))).toBe(false);
    fireEvent.click(within(top).getByTestId("admin-analysis-rerun"));
    fireEvent.click(within(top).getByRole("button", { name: "Oui, relancer" }));
    await waitFor(() => expect(calls.some((call) => call.url === `/api/admin/analyses/${ANALYSIS}/rerun`)).toBe(true));
  });

  it("shows the name of an MCP as raw text and never builds a link from it", async () => {
    fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    const top = await screen.findByTestId("admin-top");
    expect(top.querySelector("b")).toBeNull();
    expect(top.textContent).not.toContain("‮");
    expect(top.textContent).toContain("@evil/pkg");
    for (const link of document.querySelectorAll("a")) {
      expect(link.getAttribute("href")).toMatch(/^\/analyses\/[0-9a-f-]{36}$/);
    }
  });

  it("marks an alert as read", async () => {
    const calls = fakeApi();
    renderWithIntl(<Dashboard />, "fr");
    fireEvent.click(await screen.findByRole("button", { name: "Marquer comme lue" }));
    await waitFor(() => expect(calls.some((call) => call.url === `/api/admin/alerts/${ALERT}/read` && call.method === "POST")).toBe(true));
  });

  it("says when the accounts service does not answer instead of showing zero", async () => {
    fakeApi({ accountsDown: true });
    renderWithIntl(<Dashboard />, "en");
    const dial = await screen.findByTestId("admin-visits-dial");
    await waitFor(() => expect(dial.textContent).toContain("The accounts service does not answer."));
    expect(screen.queryByTestId("admin-accounts-total")).toBeNull();
  });
});

describe("the dashboard client", () => {
  it("reads only the known fields and refuses a strange answer", () => {
    expect(parseSpend({ today_usd: "1" })).toBeNull();
    expect(parseSpend(null)).toBeNull();
    expect(parseCredit({ balance_usd: 3 })).toBeNull();
    const read = parseCredit({ ...credit(3), secret: "x" });
    expect(read?.balanceUsd).toBe(3);
    expect(JSON.stringify(read)).not.toContain("secret");
  });

  it("reads a typed amount with a comma or a dot, and nothing else", () => {
    expect(parseAmount("9,75")).toBe(9.75);
    expect(parseAmount(" 12.5 ")).toBe(12.5);
    expect(parseAmount("0")).toBe(0);
    for (const typed of ["", "-1", "1e3", "abc", "1,2,3", "1234567"]) {
      expect(parseAmount(typed)).toBeNull();
    }
  });

  it("keeps a bar between empty and full", () => {
    expect(share(5, 10)).toBe(0.5);
    expect(share(15, 10)).toBe(1);
    expect(share(1, 0)).toBe(0);
    expect(share(-1, 10)).toBe(0);
  });
});
