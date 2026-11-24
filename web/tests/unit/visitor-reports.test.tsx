import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NewReportsCount, ReportsSection } from "@/components/admin/reports-section";
import { ReportBox } from "@/components/report/report-box";
import { characterCount, outcomeOf, parseReportList } from "@/lib/visitor-reports";

import { renderWithIntl, TEST_ALTCHA_PAYLOAD } from "./intl";

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

const ANALYSIS = "11111111-1111-4111-8111-111111111111";
const REPORT = "55555555-5555-4555-8555-555555555555";
const TRAPPED_COMMENT = "Look \u202E<b>here</b>\nsecond line";

type Call = { url: string; method: string; headers: Record<string, string>; body: unknown };

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function fakeFetch(reply: (call: Call) => Response): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      let body: unknown = null;
      if (typeof init?.body === "string") {
        body = JSON.parse(init.body);
      }
      const call = { url, method: init?.method ?? "GET", headers: (init?.headers ?? {}) as Record<string, string>, body };
      calls.push(call);
      return reply(call);
    }),
  );
  return calls;
}

function listed(overrides: Record<string, unknown> = {}) {
  return {
    id: REPORT,
    analysis_id: ANALYSIS,
    kind: "author_error",
    unverified: true,
    status: "new",
    comment: TRAPPED_COMMENT,
    engine_version: "0.6.1",
    rules_version: "4",
    color: "red",
    reporter_kind: "account",
    account_id: "acc-123",
    created_at: "2026-12-01T08:00:00+00:00",
    closed_at: null,
    comment_erased_at: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the report box of a report", () => {
  it("opens, asks for a kind, sends it with ALTCHA and the comment, then thanks", async () => {
    const calls = fakeFetch(() => answer(201, { ok: true }));
    renderWithIntl(<ReportBox analysisId={ANALYSIS} />, "fr");
    fireEvent.click(screen.getByRole("button", { name: "Signaler" }));
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText("Choisis d'abord ce que tu veux signaler.")).toBeTruthy();
    expect(calls).toHaveLength(0);
    expect(screen.getByText("Tu es l'auteur ? Signale une erreur")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /Danger non détecté/ }));
    fireEvent.change(screen.getByLabelText("Commentaire (facultatif)"), { target: { value: "Il écrit dans /etc" } });
    expect(screen.getByText("482 caractères restants")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText(/Merci ! Ton signalement est bien arrivé/)).toBeTruthy();
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe(`/api/analyses/${ANALYSIS}/reports`);
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.headers["x-altcha"]).toBe(TEST_ALTCHA_PAYLOAD);
    expect(calls[0]?.body).toEqual({ kind: "missed_danger", comment: "Il écrit dans /etc" });
  });

  it("sends no comment field when the comment is empty, and counts characters, not code units", async () => {
    const calls = fakeFetch(() => answer(201, { ok: true }));
    renderWithIntl(<ReportBox analysisId={ANALYSIS} />, "en");
    fireEvent.click(screen.getByRole("button", { name: "Report" }));
    fireEvent.click(screen.getByRole("radio", { name: /Needless alert/ }));
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "\u{1F600}\u{1F600}" } });
    expect(screen.getByText("498 characters left")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText(/Thank you!/);
    expect(calls[0]?.body).toEqual({ kind: "false_alarm" });
    expect(characterCount("\u{1F600}a")).toBe(2);
  });

  it.each([
    [409, "report_duplicate", {}, "Tu as déjà envoyé ce type de signalement pour ce rapport."],
    [429, "report_limit", { resets_at: "2026-12-02T00:00:00+00:00" }, /^La limite de 10 signalements par jour est atteinte\. Tu pourras en envoyer d'autres à \d{2}:\d{2}\.$/],
    [429, "report_global", {}, "La boîte est pleine, réessaie demain."],
    [403, "altcha_invalid", {}, "La vérification anti-robot n'a pas abouti. Réessaie."],
    [403, "api.account_blocked", {}, "Ce compte est bloqué."],
    [500, "anything", {}, "Le signalement n'a pas pu partir. Réessaie dans un instant."],
  ])("says plainly why a report is refused (%s %s)", async (status, code, params, message) => {
    fakeFetch(() => answer(status, { error: { code, params } }));
    renderWithIntl(<ReportBox analysisId={ANALYSIS} />, "fr");
    fireEvent.click(screen.getByRole("button", { name: "Signaler" }));
    fireEvent.click(screen.getByRole("radio", { name: /Alerte injustifiée/ }));
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Envoyer" })).toBeTruthy();
  });

  it("reads the answers of the API and nothing else", () => {
    expect(outcomeOf(201, null)).toEqual({ kind: "sent" });
    expect(outcomeOf(429, { error: { code: "report_limit", params: {} } })).toEqual({ kind: "limit", resetsAt: null });
    expect(outcomeOf(400, { error: { code: "api.comment_too_long", params: { limit: "500" } } })).toEqual({ kind: "too_long" });
    expect(outcomeOf(502, "<html>")).toEqual({ kind: "unavailable" });
  });
});

describe("the reports of the admin", () => {
  it("shows a report with its kind, the not verified mark, the versions, the color word and the comment as raw text", async () => {
    fakeFetch(() => answer(200, { reports: [listed()], new_count: 1 }));
    renderWithIntl(<ReportsSection refresh={0} onChanged={() => {}} />, "fr");
    const line = await screen.findByTestId("admin-report");
    expect(line.textContent).toContain("Erreur signalée par l'auteur");
    expect(within(line).getByTestId("admin-report-unverified").textContent).toBe("non vérifié");
    expect(line.textContent).toContain("moteur 0.6.1, règles 4");
    expect(line.textContent).toContain("Rouge (DANGER)");
    expect(within(line).getByTestId("admin-report-account").textContent).toBe("acc-123");
    const comment = within(line).getByTestId("admin-report-comment");
    expect(comment.querySelector("b")).toBeNull();
    expect(comment.textContent).toContain("<b>here</b>");
    expect(comment.textContent).not.toContain("\u202E");
    const links = [...line.querySelectorAll("a")].map((link) => link.getAttribute("href"));
    expect(links).toEqual([`/analyses/${ANALYSIS}`]);
  });

  it("says who sent it without any address, and when the comment was erased", async () => {
    fakeFetch(() =>
      answer(200, {
        reports: [
          listed({ id: "r1", kind: "false_alarm", unverified: false, reporter_kind: "anonymous", account_id: null, comment: null }),
          listed({ id: "r2", kind: "missed_danger", unverified: false, reporter_kind: "deleted", account_id: null, comment: null, status: "handled", comment_erased_at: "2026-12-01T09:00:00+00:00" }),
        ],
        new_count: 1,
      }),
    );
    renderWithIntl(<ReportsSection refresh={0} onChanged={() => {}} />, "fr");
    const lines = await screen.findAllByTestId("admin-report");
    expect(lines[0]?.textContent).toContain("Sans compte");
    expect(lines[0]?.textContent).toContain("Pas de commentaire.");
    expect(lines[1]?.textContent).toContain("Compte supprimé depuis");
    expect(lines[1]?.textContent).toContain("Commentaire effacé 90 jours après la décision.");
    expect(within(lines[0] as HTMLElement).queryByTestId("admin-report-unverified")).toBeNull();
  });

  it("filters by status and kind, and marks a report handled", async () => {
    let changed = 0;
    const calls = fakeFetch((call) => {
      if (call.method === "POST") {
        return answer(200, { id: REPORT, status: "handled" });
      }
      return answer(200, { reports: [listed()], new_count: 1 });
    });
    renderWithIntl(<ReportsSection refresh={0} onChanged={() => (changed += 1)} />, "fr");
    await screen.findByTestId("admin-report");
    fireEvent.change(screen.getByLabelText("Statut"), { target: { value: "new" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "author_error" } });
    await waitFor(() => expect(calls.some((call) => call.url === "/api/admin/reports?status=new&kind=author_error")).toBe(true));
    fireEvent.click(await screen.findByTestId("admin-report-handled"));
    await waitFor(() => expect(calls.some((call) => call.method === "POST")).toBe(true));
    const posted = calls.find((call) => call.method === "POST");
    expect(posted?.url).toBe(`/api/admin/reports/${REPORT}/status`);
    expect(posted?.body).toEqual({ status: "handled" });
    expect(await screen.findByText("C'est noté dans le journal admin.")).toBeTruthy();
    expect(changed).toBe(1);
  });

  it("counts the new reports at the top of the page", async () => {
    fakeFetch(() => answer(200, { reports: [], new_count: 3 }));
    renderWithIntl(<NewReportsCount refresh={0} />, "fr");
    expect((await screen.findByTestId("admin-new-reports")).textContent).toBe("3 signalements nouveaux");
  });

  it("refuses a strange list", () => {
    expect(parseReportList({ reports: "x", new_count: 1 })).toBeNull();
    expect(parseReportList({ reports: [{ id: 1 }], new_count: 0 })).toEqual({ reports: [], newCount: 0 });
  });
});
