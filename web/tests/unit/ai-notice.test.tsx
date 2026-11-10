import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiNoticeSlot } from "@/components/report/ai-notice-slot";
import { ReportView } from "@/components/report/report-view";
import { AI_MAX_WAIT_MILLISECONDS, AI_POLL_MILLISECONDS } from "@/components/report/use-ai-text";
import {
  parseNoticeAnswer,
  parseTranslationAnswer,
  translationOfTool,
  withPlainTitles,
  type NoticeAnswer,
} from "@/lib/ai-text";
import type { Tool } from "@/lib/analysis";

import { renderWithIntl } from "./intl";
import { loadView } from "./reports";

vi.mock("@/i18n/navigation", () => ({
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
  useRouter: () => ({ push: vi.fn() }),
}));

const ORANGE = "server-filesystem.view";
const FALLBACK = {
  variant: "tools",
  messages: [
    { code: "ai.notice.fallback.count", params: { count: "2" } },
    { code: "ai.notice.fallback.can", params: {} },
    { code: "ai.notice.fallback.unavailable", params: {} },
  ],
  actions: ["lamp.files_read.phrase", "lamp.internet.phrase"],
};
const CONTENT = {
  summary: "Ce serveur lit tes fichiers.",
  use_cases: ["Lire un dossier."],
  tool_titles: [{ tool_index: 0, title: "Lire un fichier", sentence: "Il lit un fichier." }],
  alert: null,
};

type Json = Record<string, unknown>;

function answer(status: string, extra: Json = {}): Json {
  return {
    id: "x",
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

function ready(extra: Json = {}): Json {
  return answer("ready", { source: "ai", content: { ...CONTENT, ...extra }, model: "some-model", date: "2026-11-09T10:00:00+00:00" });
}

function translation(status: string, content: Json | null = null): Json {
  let source = "ai";
  if (content === null) {
    source = "template";
  }
  return answer(status, { kind: "translation", fallback: null, content, source });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Calls = { url: string; method: string; body: string | null }[];

function serve(notice: Json[], translated: Json[] = [translation("none")]): Calls {
  const calls: Calls = [];
  const seen = { notice: 0, translation: 0 };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: (init?.body as string) ?? null });
    if (url.includes("/translation")) {
      const index = Math.min(seen.translation, translated.length - 1);
      seen.translation += 1;
      return json(translated[index]);
    }
    const index = Math.min(seen.notice, notice.length - 1);
    seen.notice += 1;
    return json(notice[index]);
  });
  return calls;
}

function parsed(value: Json): NoticeAnswer {
  const result = parseNoticeAnswer(value);
  if (result === null) {
    throw new Error("does not parse");
  }
  return result;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("the answer of the notice route", () => {
  it("is read when it has the right shape", () => {
    expect(parsed(ready()).content?.summary).toBe(CONTENT.summary);
    expect(parsed(answer("paused", { resume: "tomorrow" })).resume).toBe("tomorrow");
  });

  it.each([
    ["an unknown status", answer("sure")],
    ["an unknown resume", answer("paused", { resume: "never" })],
    ["a content without summary", answer("ready", { content: { use_cases: [], tool_titles: [] } })],
    ["a title without position", answer("ready", { content: { ...CONTENT, tool_titles: [{ title: "a", sentence: "b" }] } })],
    ["a list", []],
  ])("is refused with %s", (_name, value) => {
    expect(parseNoticeAnswer(value)).toBeNull();
  });

  it("gives its titles to the tools by position, and nothing else changes", () => {
    const tools = [{ name: "a", plain_title: null, plain_sentence: null }, { name: "b", plain_title: null, plain_sentence: null }] as Tool[];
    const titled = withPlainTitles(tools, parsed(ready()));
    expect(titled[0].plain_title).toBe("Lire un fichier");
    expect(titled[0].plain_sentence).toBe("Il lit un fichier.");
    expect(titled[1].plain_title).toBeNull();
    expect(withPlainTitles(tools, parsed(answer("failed")))).toBe(tools);
    expect(withPlainTitles(tools, null)).toBe(tools);
  });

  it("gives each tool its translation and those of its parameters by identifier", () => {
    const value = parseTranslationAnswer(
      translation("ready", {
        items: [
          { id: "tool_1", text: "Bonjour" },
          { id: "tool_1_param_1", text: "Fuseau" },
          { id: "tool_2_param_0", text: "Seul" },
        ],
      }),
    );
    expect(translationOfTool(value, 1, 2)).toEqual({ description: "Bonjour", parameters: [null, "Fuseau"] });
    expect(translationOfTool(value, 2, 1)).toEqual({ description: null, parameters: ["Seul"] });
    expect(translationOfTool(value, 0, 3)).toBeNull();
    expect(translationOfTool(null, 0, 0)).toBeNull();
  });
});

describe("the notice block", () => {
  it("marks the AI text and says what the AI read, in French", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(ready())} waiting={false} />, "fr");
    expect(screen.getByText(CONTENT.summary)).toBeTruthy();
    expect(screen.getByText("Résumé automatique")).toBeTruthy();
    expect(container.textContent).toContain(
      "Écrit par une IA à partir de ce que MCPlain a trouvé. L'IA n'a lu ni le code ni les textes de l'auteur, et ne change jamais le verdict.",
    );
    expect(container.querySelector("[data-ai-alert]")).toBeNull();
  });

  it("says the same in English", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(ready())} waiting={false} />, "en");
    expect(screen.getByText("Automatic summary")).toBeTruthy();
    expect(container.textContent).toContain("The AI read neither the code nor the author's texts");
  });

  it("shows the alert in a neutral block, never in a verdict color", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(ready({ alert: "Une météo qui lit des secrets, c'est étonnant." }))} waiting={false} />, "fr");
    const block = container.querySelector("[data-ai-alert]");
    expect(block?.textContent).toContain("Avis de l'IA");
    expect(block?.textContent).toContain("c'est étonnant");
    const classes = Array.from(container.querySelectorAll("*")).map((node) => node.getAttribute("class") ?? "").join(" ");
    expect(classes).not.toMatch(/\b(?:bg|text|stroke|shadow|border)-(?:green|warn|red|gray|lamp|chip)/);
    expect(block?.closest("[data-verdict]")).toBeNull();
  });

  it.each([
    ["an empty alert", ""],
    ["an alert of spaces", "   "],
    ["no alert", null],
  ])("shows no opinion and no reassuring word with %s", (_name, alert) => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(ready({ alert }))} waiting={false} />, "fr");
    expect(container.querySelector("[data-ai-alert]")).toBeNull();
    expect(container.textContent).not.toContain("Avis de l'IA");
    expect(container.textContent?.toLowerCase()).not.toMatch(/tout va bien|aucun problème|sans danger|sûr/);
  });

  it("writes third-party-looking text as plain text", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(ready({ summary: "<img src=x>" }))} waiting={false} />, "fr");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x>");
  });

  it("shows the fallback made from text codes and lamps", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(answer("failed"))} waiting={false} />, "fr");
    const text = container.querySelector("[data-notice-fallback]")?.textContent ?? "";
    expect(text).toContain("MCPlain a reconnu 2 outil(s) dans ce serveur.");
    expect(text).toContain("Il peut lire tes fichiers et aller sur Internet.");
    expect(text).toContain("MCPlain n'a pas pu écrire de résumé automatique pour ce serveur.");
    expect(screen.queryByText("Résumé automatique")).toBeNull();
  });

  it("shows the variant without any tool", () => {
    const fallback = { variant: "no_tools", messages: [{ code: "ai.notice.fallback.no_tools", params: {} }], actions: [] };
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(answer("template", { fallback }))} waiting={false} />, "fr");
    expect(container.querySelector('[data-notice-fallback="no_tools"]')?.textContent).toContain("n'a reconnu aucun outil");
  });

  it.each([
    ["tomorrow", "La notice automatique revient demain."],
    ["next_month", "La notice automatique revient le mois prochain."],
    ["later", "La notice automatique revient bientôt."],
  ])("says when a paused notice comes back: %s", (resume, sentence) => {
    renderWithIntl(<AiNoticeSlot answer={parsed(answer("paused", { resume }))} waiting={false} />, "fr");
    expect(screen.getByText(sentence)).toBeTruthy();
  });

  it("has no animation when the visitor asks for reduced motion", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={parsed(answer("pending"))} waiting />, "fr");
    expect(container.querySelector("[data-notice-pending] span")?.className).toContain("motion-reduce:animate-none");
  });

  it("shows nothing when the API gave no usable answer", () => {
    const { container } = renderWithIntl(<AiNoticeSlot answer={null} waiting={false} />, "fr");
    expect(container.childElementCount).toBe(0);
  });
});

describe("the report page", () => {
  it("asks for the notice when it opens, in the language of the page", async () => {
    const calls = serve([ready()], [translation("template")]);
    const { container } = renderWithIntl(<ReportView analysis={loadView(ORANGE)} />, "en");
    await waitFor(() => expect(container.querySelector('[data-notice="ready"]')).not.toBeNull());
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toMatch(/\/api\/analyses\/[^/]+\/notice$/);
    expect(calls[0].body).toBe(JSON.stringify({ lang: "en" }));
    expect(calls.some((call) => call.url.includes("/translation"))).toBe(false);
  });

  it("asks for the French translation on a French page only", async () => {
    const calls = serve([ready()], [translation("template")]);
    const { container } = renderWithIntl(<ReportView analysis={loadView(ORANGE)} />, "fr");
    await waitFor(() => expect(container.querySelector('[data-notice="ready"]')).not.toBeNull());
    await waitFor(() => expect(calls.some((call) => call.url.includes("/translation") && call.body === JSON.stringify({ lang: "fr" }))).toBe(true));
  });

  it("asks nothing for a failed analysis", async () => {
    const calls = serve([ready()]);
    const failed = loadView("npm-not-found.view");
    renderWithIntl(<ReportView analysis={failed} />, "fr");
    await act(async () => {});
    expect(calls).toEqual([]);
  });

  it("gets the titles into the grid and the sheet, and leaves the color and the lamps alone", async () => {
    serve([ready()], [translation("template")]);
    const view = loadView(ORANGE);
    const before = renderWithIntl(<ReportView analysis={view} />, "en");
    const verdict = before.container.querySelector("[data-verdict]")?.textContent;
    const lamps = Array.from(before.container.querySelectorAll("[data-lamp]")).map((lamp) => lamp.textContent);
    await waitFor(() => expect(before.container.querySelector('[data-tool-card="0"]')?.textContent).toContain("Lire un fichier"));
    expect(before.container.querySelector('[data-tool-card="0"]')?.textContent).toContain("Automatic summary");
    expect(before.container.querySelector('[data-tool-card="1"]')?.textContent).not.toContain("Automatic summary");
    expect(before.container.querySelector("[data-verdict]")?.textContent).toBe(verdict);
    expect(Array.from(before.container.querySelectorAll("[data-lamp]")).map((lamp) => lamp.textContent)).toEqual(lamps);
  });

  it("polls every 2 seconds until the notice is ready", async () => {
    vi.useFakeTimers();
    const calls = serve([answer("pending"), answer("pending"), ready()], [translation("template")]);
    const { container } = renderWithIntl(<ReportView analysis={loadView(ORANGE)} />, "en");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(container.querySelector("[data-notice-pending]")).not.toBeNull();
    expect(container.querySelector("[data-notice-fallback]")).not.toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AI_POLL_MILLISECONDS * 2);
    });
    expect(container.querySelector('[data-notice="ready"]')).not.toBeNull();
    expect(container.querySelector("[data-notice-pending]")).toBeNull();
    const noticeCalls = calls.filter((call) => call.url.includes("/notice"));
    expect(noticeCalls.map((call) => call.method)).toEqual(["POST", "GET", "GET"]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AI_POLL_MILLISECONDS * 3);
    });
    expect(calls.filter((call) => call.url.includes("/notice"))).toHaveLength(3);
  });

  it("stops after 30 seconds and keeps the fallback", async () => {
    vi.useFakeTimers();
    const calls = serve([answer("pending")], [translation("template")]);
    const { container } = renderWithIntl(<ReportView analysis={loadView(ORANGE)} />, "en");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AI_MAX_WAIT_MILLISECONDS + AI_POLL_MILLISECONDS);
    });
    expect(container.querySelector("[data-notice-pending]")).toBeNull();
    expect(container.querySelector("[data-notice-fallback]")).not.toBeNull();
    const count = calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AI_POLL_MILLISECONDS * 5);
    });
    expect(calls).toHaveLength(count);
    expect(count).toBeLessThanOrEqual(17);
  });

  it("shows nothing when the API refuses, and the report stays whole", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => json({ error: { code: "api.not_found", params: {} } }, 404));
    const { container } = renderWithIntl(<ReportView analysis={loadView(ORANGE)} />, "fr");
    await act(async () => {});
    expect(container.querySelector("[data-notice]")).toBeNull();
    expect(container.querySelector("[data-verdict]")).not.toBeNull();
  });
});

describe("the translation in the sheet", () => {
  async function openSheet(items: { id: string; text: string }[] | null, status = "ready") {
    let content: Json | null = null;
    if (items !== null) {
      content = { items };
    }
    serve([answer("failed")], [translation(status, content)]);
    const view = loadView(ORANGE);
    const rendered = renderWithIntl(<ReportView analysis={view} />, "fr");
    const tool = view.result?.servers[0].tools.findIndex((entry) => entry.description.trim() !== "") ?? 0;
    fireEvent.click(rendered.container.querySelector(`[data-tool-card="${tool}"]`) as Element);
    await act(async () => {});
    return { ...rendered, tool, original: view.result?.servers[0].tools[tool].description ?? "" };
  }

  it("shows the translation with its mark, the original one click away", async () => {
    const { container, original } = await openSheet(
      Array.from({ length: 30 }, (_, index) => ({ id: `tool_${index}`, text: "Lit un fichier." })),
    );
    await waitFor(() => expect(container.querySelector('[data-translated="true"]')).not.toBeNull());
    expect(container.querySelector('[data-translated="true"]')?.textContent).toBe(
      "Traduction automatique du texte de l'auteur, pas un avis de MCPlain",
    );
    expect(container.querySelector("[data-description]")?.textContent).toContain("Lit un fichier.");
    fireEvent.click(screen.getByRole("button", { name: "Voir l'original" }));
    expect(container.querySelector('[data-translated="false"]')?.textContent).toBe("Texte de l'auteur");
    expect(container.querySelector("[data-description]")?.textContent).toContain(original.slice(0, 40));
    fireEvent.click(screen.getByRole("button", { name: "Voir la traduction" }));
    expect(container.querySelector('[data-translated="true"]')).not.toBeNull();
  });

  it("translates the parameters, keeps the original of an untranslated one, and switches the whole card", async () => {
    const view = loadView(ORANGE);
    const tool = view.result?.servers[0].tools[0];
    const tail = tool?.parameters[1].description ?? "";
    const head = tool?.parameters[2].description ?? "";
    serve([answer("failed")], [
      translation("ready", {
        items: [
          { id: "tool_0", text: "Lit tout le contenu d'un fichier." },
          { id: "tool_0_param_1", text: "Si présent, ne renvoie que les N dernières lignes." },
        ],
      }),
    ]);
    const { container } = renderWithIntl(<ReportView analysis={view} />, "fr");
    fireEvent.click(container.querySelector('[data-tool-card="0"]') as Element);
    await waitFor(() => expect(container.querySelector('[data-translated="true"]')).not.toBeNull());
    const card = () => container.querySelector("[data-announced]") as Element;
    const parameter = (index: number) => card().querySelector(`[data-parameter="${index}"]`) as Element;
    expect(card().querySelectorAll("[data-translated]")).toHaveLength(1);
    expect(card().firstElementChild?.nextElementSibling?.getAttribute("data-translated")).toBe("true");
    expect(parameter(1).textContent).toContain("Si présent, ne renvoie que les N dernières lignes.");
    expect(parameter(1).getAttribute("data-parameter-translated")).toBe("true");
    expect(parameter(2).textContent).toContain(head.slice(0, 30));
    expect(parameter(2).getAttribute("data-parameter-translated")).toBe("false");
    expect(parameter(1).textContent).toContain("tail");
    fireEvent.click(screen.getByRole("button", { name: "Voir l'original" }));
    expect(card().querySelector('[data-translated="false"]')?.textContent).toBe("Texte de l'auteur");
    expect(card().querySelector("[data-description]")?.textContent).toContain("Read the complete contents");
    expect(parameter(1).textContent).toContain(tail.slice(0, 30));
    expect(parameter(1).getAttribute("data-parameter-translated")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Voir la traduction" }));
    expect(parameter(1).textContent).toContain("Si présent");
    expect(card().querySelector("[data-description]")?.textContent).toContain("Lit tout le contenu");
  });

  it("shows a translated parameter even when the tool description is not translated", async () => {
    const view = loadView(ORANGE);
    serve([answer("failed")], [translation("ready", { items: [{ id: "tool_0_param_2", text: "Les N premières lignes." }] })]);
    const { container } = renderWithIntl(<ReportView analysis={view} />, "fr");
    fireEvent.click(container.querySelector('[data-tool-card="0"]') as Element);
    await waitFor(() => expect(container.querySelector('[data-translated="true"]')).not.toBeNull());
    expect(container.querySelector("[data-description]")?.textContent).toContain("Read the complete contents");
    expect(container.querySelector('[data-parameter="2"]')?.textContent).toContain("Les N premières lignes.");
  });

  it("keeps the original when the translation is rejected", async () => {
    const { container, original } = await openSheet(null, "rejected");
    await act(async () => {});
    expect(container.querySelector("[data-translated]")).toBeNull();
    expect(screen.queryByRole("button", { name: "Voir l'original" })).toBeNull();
    expect(container.querySelector("[data-description]")?.textContent).toContain(original.slice(0, 40));
  });
});
