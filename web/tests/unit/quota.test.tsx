import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisField } from "@/components/analysis-field";
import { HistorySection } from "@/components/account/history-section";
import { QuotaLine } from "@/components/quota-counter";
import { QuotaExhausted } from "@/components/report/quota-exhausted";
import type { VisitorServices } from "@/components/visitor-context";
import { startAnalysis } from "@/lib/api-client";
import { nextMidnightUtc, parseHistory, parseQuota, type QuotaInfo } from "@/lib/quota";

import { renderWithIntl, TEST_ALTCHA_PAYLOAD, TEST_VISITOR } from "./intl";

const push = vi.fn();

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push }),
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const ID = "8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";
const RESETS_AT = "2026-11-13T00:00:00+00:00";
const LOCAL_RESET = new Intl.DateTimeFormat("fr", { hour: "2-digit", minute: "2-digit" }).format(new Date(RESETS_AT));
const TRAP = "uvx demo\u202E<b>bold</b>";

function quota(kind: QuotaInfo["kind"], limit: number | null, used: number): QuotaInfo {
  let remaining: number | null = null;
  if (limit !== null) {
    remaining = limit - used;
  }
  return { kind, limit, used, remaining, resetsAt: RESETS_AT };
}

function answer(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

function submit(value: string) {
  fireEvent.change(screen.getByLabelText("MCP server link"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "ANALYZE" }));
}

beforeEach(() => {
  push.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the counter of the header", () => {
  it("says what is left without account, when it comes back, and the sentence of the shared network", () => {
    renderWithIntl(<QuotaLine quota={quota("anonymous", 3, 1)} />, "fr");
    const counter = screen.getByTestId("quota-counter");
    expect(counter.textContent).toContain("2 analyses restantes aujourd'hui");
    expect(counter.textContent).toContain(`Elles reviennent à ${LOCAL_RESET}`);
    expect(screen.getByTestId("shared-network").textContent).toBe(
      "Réseau partagé (entreprise, open space, école…) ? Crée un compte gratuit : 10 analyses par jour rien que pour toi",
    );
    expect(screen.getByTestId("shared-network").getAttribute("href")).toBe("/account/sign-up");
    expect(counter.querySelectorAll('[data-box="left"]')).toHaveLength(2);
    expect(counter.querySelectorAll('[data-box="used"]')).toHaveLength(1);
  });

  it("gives the sentence of the shared network in English too", () => {
    renderWithIntl(<QuotaLine quota={quota("anonymous", 3, 0)} />);
    expect(screen.getByTestId("quota-counter").textContent).toContain("3 analyses left today");
    expect(screen.getByTestId("quota-counter").textContent).not.toContain("come back");
    expect(screen.getByTestId("shared-network").textContent).toBe(
      "Shared network (company, open space, school…)? Create a free account: 10 analyses a day, just for you.",
    );
  });

  it("counts the ten of an account, without the sentence of the shared network", () => {
    renderWithIntl(<QuotaLine quota={quota("account", 10, 9)} />, "fr");
    expect(screen.getByTestId("quota-counter").textContent).toContain("1 analyse restante aujourd'hui");
    expect(screen.queryByTestId("shared-network")).toBeNull();
    expect(screen.getByTestId("quota-counter").querySelectorAll("[data-box]")).toHaveLength(10);
  });

  it("says that the admin and the bench have no limit", () => {
    renderWithIntl(<QuotaLine quota={quota("admin", null, 0)} />, "fr");
    expect(screen.getByTestId("quota-counter").textContent).toBe("Admin : sans limite");
    renderWithIntl(<QuotaLine quota={quota("bench", null, 0)} />);
    expect(screen.getAllByTestId("quota-counter")[1].textContent).toBe("Bench account: no limit");
  });

  it("reads only well formed answers of the quota", () => {
    expect(parseQuota({ kind: "anonymous", limit: 3, used: 1, remaining: 2, resets_at: RESETS_AT })).toEqual(quota("anonymous", 3, 1));
    expect(parseQuota({ kind: "admin", limit: null, used: 0, remaining: null, resets_at: RESETS_AT })?.kind).toBe("admin");
    expect(parseQuota({ kind: "anonymous", limit: null, used: 0, remaining: null, resets_at: RESETS_AT })).toBeNull();
    expect(parseQuota({ kind: "root", limit: 3, used: 0, remaining: 3, resets_at: RESETS_AT })).toBeNull();
    expect(parseQuota({ kind: "account", limit: 10, used: -1, remaining: 3, resets_at: RESETS_AT })).toBeNull();
    expect(nextMidnightUtc(new Date("2026-11-12T23:59:00Z"))).toBe("2026-11-13T00:00:00.000Z");
  });
});

describe("a used-up quota", () => {
  it("offers an account to a visitor without account, and keeps the cache open", () => {
    renderWithIntl(<QuotaExhausted quota={quota("anonymous", 3, 3)} />, "fr");
    const page = screen.getByTestId("quota-exhausted");
    expect(page.textContent).toContain(`Elles reviennent à ${LOCAL_RESET}.`);
    expect(page.textContent).toContain("Les MCP déjà analysés restent consultables.");
    expect(screen.getByTestId("quota-create-account").textContent).toBe("Créer un compte");
    expect(screen.getByTestId("quota-create-account").getAttribute("href")).toBe("/account/sign-up");
    expect(page.querySelector("[aria-label^='Jauge']")).toBeNull();
    expect(page.textContent).not.toContain("NON VÉRIFIÉ");
  });

  it("tells an account its ten analyses and when they come back", () => {
    renderWithIntl(<QuotaExhausted quota={quota("account", 10, 10)} />, "fr");
    const page = screen.getByTestId("quota-exhausted");
    expect(page.textContent).toContain(`Tu as utilisé tes 10 analyses du jour. Elles reviennent à ${LOCAL_RESET}.`);
    expect(page.textContent).toContain("Les MCP déjà analysés restent consultables.");
    expect(screen.queryByTestId("quota-create-account")).toBeNull();
  });
});

describe("the refusals of an analysis request", () => {
  it("sends a fresh ALTCHA solution with each request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(202, { id: ID, state: "queued", cache_only: false }));
    renderWithIntl(<AnalysisField variant="hero" />);
    submit("uvx mcp-server-fetch");
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/analyses/${ID}`));
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("x-altcha")).toBe(TEST_ALTCHA_PAYLOAD);
  });

  it("says how many minutes to wait after too many requests", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      answer(429, { error: { code: "burst_limit", params: { retry_after: "170", minutes: "3" } } }, { "Retry-After": "170" }),
    );
    renderWithIntl(<AnalysisField variant="hero" />, "fr");
    fireEvent.change(screen.getByLabelText("Lien du serveur MCP"), { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.click(screen.getByRole("button", { name: "ANALYSER" }));
    await waitFor(() =>
      expect(document.getElementById("home-error")?.textContent).toBe("Trop de demandes en peu de temps. Réessaie dans 3 minutes."),
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("says the robot check failed, when the API refuses it or when it cannot be solved", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(403, { error: { code: "altcha_invalid", params: {} } }));
    renderWithIntl(<AnalysisField variant="hero" />, "fr");
    fireEvent.change(screen.getByLabelText("Lien du serveur MCP"), { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.click(screen.getByRole("button", { name: "ANALYSER" }));
    const message = "La vérification anti-robot n'a pas abouti. Réessaie.";
    await waitFor(() => expect(document.getElementById("home-error")?.textContent).toBe(message));
    fetchMock.mockClear();
    const unsolved: VisitorServices = { ...TEST_VISITOR, solveAltcha: async () => null };
    renderWithIntl(<AnalysisField variant="header" />, "fr", undefined, unsolved);
    const field = screen.getAllByLabelText("Lien du serveur MCP à analyser")[0];
    fireEvent.change(field, { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.submit(field.closest("form") as HTMLFormElement);
    await waitFor(() => expect(screen.getAllByText(message).length).toBeGreaterThan(1));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reads a cache-only answer and a burst refusal without minutes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(answer(202, { id: ID, state: "queued", cache_only: true }));
    expect(await startAnalysis("uvx a", null, "P")).toEqual({ kind: "accepted", id: ID, cacheOnly: true });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(answer(429, { error: { code: "burst_limit", params: {} } }, { "Retry-After": "61" }));
    expect(await startAnalysis("uvx a", null, "P")).toEqual({ kind: "burst", minutes: 2 });
  });
});

describe("the history of the account", () => {
  const entries = [
    { date: "2026-11-12T09:00:00+00:00", id: ID, input: TRAP, select: null, state: "done", color: "orange", status: "ok", from_cache: true },
    { date: "2026-11-12T08:00:00+00:00", id: ID, input: "uvx b", select: null, state: "failed", color: "gray", status: null, from_cache: false },
  ];

  it("lists each analysis with its input as raw text, its word, its link and the cache mention", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(200, { entries }));
    renderWithIntl(<HistorySection />, "fr");
    await waitFor(() => expect(screen.getAllByTestId("history-entry")).toHaveLength(2));
    const [first, second] = screen.getAllByTestId("history-entry");
    expect(first.querySelector("b")).toBeNull();
    expect(first.textContent).toContain("<b>bold</b>");
    expect(first.querySelector("[data-color='orange']")?.textContent).toBe("À VÉRIFIER");
    expect(first.textContent).toContain("depuis le cache");
    expect(first.querySelector("a")?.getAttribute("href")).toBe(`/analyses/${ID}`);
    expect(second.querySelector("[data-color='gray']")?.textContent).toBe("NON VÉRIFIÉ");
    expect(second.textContent).not.toContain("depuis le cache");
  });

  it("clears the history only after a confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(200, { entries }));
    renderWithIntl(<HistorySection />, "fr");
    await waitFor(() => expect(screen.getAllByTestId("history-entry")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "EFFACER MON HISTORIQUE" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValue(answer(200, { deleted: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "OUI, EFFACER" }));
    await waitFor(() => expect(screen.getByTestId("history-empty").textContent).toBe("Aucune analyse pour l'instant."));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/account/history");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("DELETE");
  });

  it("refuses a malformed history", () => {
    expect(parseHistory({ entries: [{ id: ID }] })).toBeNull();
    expect(parseHistory({})).toBeNull();
    expect(parseHistory({ entries: [] })).toEqual([]);
  });
});
