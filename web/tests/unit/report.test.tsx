import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Gauge } from "@/components/report/gauge";
import { LampCluster } from "@/components/report/lamp-cluster";
import { ReportView } from "@/components/report/report-view";
import { ToolGrid } from "@/components/report/tool-grid";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { parseAnalysisView, type Server } from "@/lib/analysis";
import { THEME_STORAGE_KEY } from "@/lib/theme";

import { renderWithIntl } from "./intl";
import { loadView, rawView } from "./reports";

const push = vi.fn();

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push }),
}));

const NEW_ID = "9c8b7a65-4321-4fed-8cba-987654321000";
const ORANGE = "server-filesystem.view";
const RED = "postmark-like.result";
const GREEN_DOMAINS = "fixed-domains.result";
const FAILED = "npm-not-found.view";
const MULTIPLE = "modelcontextprotocol-servers.view";
const TRAP_MARK = "TRAP";
const BIDI = "‮";
const THIRD_PARTY_KEYS = new Set([
  "name",
  "description",
  "title",
  "file",
  "function",
  "snippet",
  "quote",
  "detail",
  "url",
  "domain",
  "match",
  "command",
  "path",
  "version",
  "requested_version",
  "revision",
  "reference",
  "subdir",
  "integrity",
  "repository",
  "hidden_text",
  "tool",
  "input",
  "select",
  "plain_title",
  "plain_sentence",
]);
const THIRD_PARTY_LISTS = new Set(["internet_domains", "contacted_domains", "ignored_arguments"]);

function server(file: string): Server {
  const view = loadView(file);
  const result = view.result;
  if (result === null || result.servers.length === 0) {
    throw new Error("no server");
  }
  return result.servers[0];
}

function trapper() {
  const traps = new Map<string, string>();
  return (value: string) => {
    let trap = traps.get(value);
    if (trap === undefined) {
      trap = `<b>${TRAP_MARK}${traps.size}</b>${BIDI}`;
      traps.set(value, trap);
    }
    return trap;
  };
}

function trapThirdParty(value: unknown, trap: (text: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => trapThirdParty(item, trap));
  }
  if (typeof value !== "object" || value === null) {
    return value;
  }
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (THIRD_PARTY_KEYS.has(key) && typeof item === "string") {
      result[key] = trap(item);
    } else if (THIRD_PARTY_LISTS.has(key) && Array.isArray(item)) {
      result[key] = item.map((entry) => trap(String(entry)));
    } else if (key === "params" && typeof item === "object" && item !== null) {
      result[key] = Object.fromEntries(Object.entries(item).map(([name, text]) => [name, trap(String(text))]));
    } else {
      result[key] = trapThirdParty(item, trap);
    }
  }
  return result;
}

function textNodes(root: Node): Text[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) {
    nodes.push(walker.currentNode as Text);
  }
  return nodes;
}

describe("gauge", () => {
  it.each([
    ["green", "-60"],
    ["orange", "0"],
    ["red", "60"],
  ] as const)("puts the needle of a %s verdict at %s degrees and fills only its zone", (color, angle) => {
    const { container } = renderWithIntl(<Gauge color={color} word="WORD" />);
    expect(container.querySelector("[data-needle]")?.getAttribute("data-needle")).toBe(angle);
    const zones = Array.from(container.querySelectorAll("[data-zone]"));
    expect(zones).toHaveLength(3);
    for (const zone of zones) {
      const active = zone.getAttribute("data-zone") === color;
      expect(zone.getAttribute("data-active")).toBe(String(active));
      let expected = "opacity-22";
      if (active) {
        expected = "opacity-100";
      }
      expect(zone.getAttribute("class")).toContain(expected);
    }
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Verdict gauge: WORD");
  });

  it("shows no needle for a gray verdict, and the three zones at 22 %", () => {
    const { container } = renderWithIntl(<Gauge color="gray" word="NOT VERIFIED" />);
    expect(container.querySelector("[data-needle]")).toBeNull();
    expect(container.querySelectorAll("circle")).toHaveLength(0);
    for (const zone of container.querySelectorAll("[data-zone]")) {
      expect(zone.getAttribute("class")).toContain("opacity-22");
    }
  });
});

describe("lamps", () => {
  it("shows off, on and danger lamps with their written state and the count", () => {
    const { container } = renderWithIntl(<LampCluster server={server(RED)} />, "fr");
    const internet = container.querySelector('[data-lamp="internet"]');
    expect(internet?.getAttribute("data-state")).toBe("danger");
    expect(internet?.textContent).toContain("Danger");
    expect(internet?.textContent).toContain("Copie cachée de tes e-mails");
    const files = container.querySelector('[data-lamp="files_read"]');
    expect(files?.getAttribute("data-state")).toBe("off");
    expect(files?.textContent).toContain("Éteint");
    expect(container.textContent).toContain("1 allumé sur 6, dont 1 en danger");
  });

  it("notes the fixed domains of an internet lamp that is on", () => {
    const { container } = renderWithIntl(<LampCluster server={server(GREEN_DOMAINS)} />, "fr");
    const internet = container.querySelector('[data-lamp="internet"]');
    expect(internet?.getAttribute("data-state")).toBe("on");
    expect(internet?.textContent).toContain("Allumé");
    expect(internet?.textContent).toContain("Seulement");
    expect(internet?.querySelector("[data-raw-text]")).not.toBeNull();
  });
});

describe("tool cards", () => {
  it("rings warn tools in orange, danger tools in red, and the selected one in blue", () => {
    const tools = server(ORANGE).tools;
    const warn = tools.findIndex((tool) => tool.level === "warn");
    const plain = tools.findIndex((tool) => tool.level === "none");
    const first = renderWithIntl(<ToolGrid tools={tools} selected={plain} onPick={() => {}} />);
    const card = (index: number) => first.container.querySelector(`[data-tool-card="${index}"]`);
    expect(card(warn)?.className).toContain("shadow-warn-ring");
    expect(card(plain)?.className).toContain("shadow-sel-ring");
    expect(card(plain)?.getAttribute("aria-current")).toBe("true");
    first.unmount();
    const second = renderWithIntl(<ToolGrid tools={tools} selected={warn} onPick={() => {}} />);
    expect(second.container.querySelector(`[data-tool-card="${warn}"]`)?.className).toContain("shadow-sel-ring");
    second.unmount();
    const danger = server(RED).tools;
    const red = renderWithIntl(<ToolGrid tools={danger} selected={-1} onPick={() => {}} />);
    expect(red.container.querySelector('[data-level="danger"]')?.className).toContain("shadow-red-ring");
  });

  it("says what the code of a tool can do from its lamps, or that no lamp is lit", () => {
    const tools = server(ORANGE).tools;
    const { container } = renderWithIntl(<ToolGrid tools={tools} selected={0} onPick={() => {}} />, "fr");
    const writer = tools.findIndex((tool) => tool.level === "warn");
    expect(container.querySelector(`[data-tool-card="${writer}"]`)?.textContent).toContain(
      "Peut lire tes fichiers et modifier tes fichiers.",
    );
    const quiet = tools.findIndex((tool) => tool.lamps.every((lamp) => lamp.state === "off"));
    expect(container.querySelector(`[data-tool-card="${quiet}"]`)?.textContent).toContain("Aucun voyant allumé");
  });
});

describe("report view", () => {
  beforeEach(() => {
    push.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists several servers without any verdict", () => {
    const { container } = renderWithIntl(<ReportView analysis={loadView(MULTIPLE)} />, "fr");
    expect(container.querySelector("[data-verdict]")).toBeNull();
    expect(container.querySelector("[data-gauge]")).toBeNull();
    expect(container.textContent).toContain("Rien n'a encore été analysé : choisis-en un.");
    expect(container.querySelectorAll("[data-candidates] button").length).toBeGreaterThan(1);
    expect(container.querySelectorAll("[data-candidates] button").length).toBeLessThanOrEqual(50);
  });

  it("runs a failed analysis again with the same input and selection", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: NEW_ID, state: "queued" }), { status: 202 }));
    vi.stubGlobal("fetch", fetch);
    const view = loadView(FAILED);
    renderWithIntl(<ReportView analysis={{ ...view, select: "src/a" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Run again" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/analyses/${NEW_ID}`));
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ input: view.input, select: "src/a" });
  });

  it("has no Run again button on a finished report", () => {
    renderWithIntl(<ReportView analysis={loadView(ORANGE)} />);
    expect(screen.queryByRole("button", { name: "Run again" })).toBeNull();
  });

  it.each([ORANGE, RED, GREEN_DOMAINS, FAILED, MULTIPLE])("shows every third-party field of %s with RawText", (file) => {
    const trapped = trapThirdParty(rawView(file), trapper()) as Record<string, unknown>;
    const view = parseAnalysisView({ ...trapped, id: rawView(file).id });
    expect(view).not.toBeNull();
    const { container } = renderWithIntl(<ReportView analysis={view!} />);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).not.toContain(BIDI);
    const trappedNodes = textNodes(container).filter((node) => node.data.includes(TRAP_MARK));
    expect(trappedNodes.length).toBeGreaterThan(0);
    for (const node of trappedNodes) {
      expect(node.parentElement?.closest("[data-raw-text]"), node.data).not.toBeNull();
    }
    expect(container.querySelectorAll('[data-invisible="U+202E"]').length).toBeGreaterThan(0);
  });
});

describe("theme switcher", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.className = "";
  });

  it("keeps the choice in localStorage, sets the class on html, and reads it back", () => {
    const first = renderWithIntl(<ThemeSwitcher />);
    expect(screen.getByRole("button", { name: "System" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("th-dark")).toBe(true);
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("true");
    first.unmount();
    document.documentElement.className = "";
    renderWithIntl(<ThemeSwitcher />);
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.classList.contains("th-dark")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.className).toBe("");
  });
});
