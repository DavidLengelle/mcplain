import { readFileSync } from "node:fs";
import { join } from "node:path";

import { screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/[locale]/page";
import { ChapterExample } from "@/components/home/chapter-example";
import { SiteHeader } from "@/components/site-header";
import { parseAnalysisResult, type AnalysisResult } from "@/lib/analysis";
import { CHAPTER_IDS, GUIDE_SOURCES, TOOL_ZONE_ID } from "@/lib/constants";
import { EXAMPLE_REPORT, EXAMPLE_REPORT_DATA } from "@/lib/example-report";

import { renderWithIntl } from "./intl";

const navigation = vi.hoisted(() => ({ pathname: "/" }));

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => navigation.pathname,
  Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const ANALYSIS_PATH = "/analyses/8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";
const RULES_VERSION_PATTERN = /^RULES_VERSION = "([^"]+)"$/m;

type Tree = { [key: string]: string | Tree };

function engineRulesVersion(): string {
  const source = readFileSync(join(process.cwd(), "..", "engine", "src", "mcplain", "verdict.py"), "utf-8");
  const match = RULES_VERSION_PATTERN.exec(source);
  if (match === null) {
    throw new Error("RULES_VERSION is missing from the engine");
  }
  return match[1];
}

function keys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    if (typeof value === "string") {
      return [`${prefix}${key}`];
    }
    return keys(value, `${prefix}${key}.`);
  });
}

function homeKeys(language: string): string[] {
  const messages = JSON.parse(readFileSync(join(process.cwd(), "messages", `${language}.json`), "utf-8")) as Tree;
  return keys(messages.home as Tree).sort();
}

function toolZone(): HTMLElement {
  const zone = document.getElementById(TOOL_ZONE_ID);
  if (zone === null) {
    throw new Error("the tool zone is missing");
  }
  return zone;
}

function exampleReport(): AnalysisResult {
  if (EXAMPLE_REPORT === null) {
    throw new Error("the example report does not follow the engine output");
  }
  return EXAMPLE_REPORT;
}

describe("site header", () => {
  beforeEach(() => {
    navigation.pathname = "/";
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each(["en", "fr"])("has no analysis field on the home page (%s)", (locale) => {
    renderWithIntl(<SiteHeader />, locale);
    expect(document.getElementById("header-input")).toBeNull();
    expect(document.querySelector("#site-header form")).toBeNull();
  });

  it("keeps its analysis field on a report page", () => {
    navigation.pathname = ANALYSIS_PATH;
    renderWithIntl(<SiteHeader />);
    expect(screen.getByLabelText("Link of the MCP server to analyze").id).toBe("header-input");
    expect(screen.getByRole("button", { name: "ANALYZE" })).toBeDefined();
  });
});

describe("home page", () => {
  beforeEach(() => {
    navigation.pathname = "/";
  });

  it("has one h1, in the tool zone, and the guide titles in h2", () => {
    renderWithIntl(<HomePage />);
    const titles = document.querySelectorAll("h1");
    expect(titles).toHaveLength(1);
    expect(toolZone().contains(titles[0])).toBe(true);
    const guideTitles = Array.from(document.querySelectorAll("h2")).map((title) => title.id);
    expect(guideTitles).toEqual(["h-guide", ...CHAPTER_IDS.map((id) => `h-${id}`), "h-fin"]);
  });

  it("has the nine chapters with their stable ids, in order", () => {
    renderWithIntl(<HomePage />);
    const chapters = Array.from(document.querySelectorAll("section[data-chapter]")).map((chapter) => chapter.id);
    expect(chapters).toEqual([...CHAPTER_IDS]);
  });

  it("links every entry of the table of contents to an existing chapter", () => {
    renderWithIntl(<HomePage />);
    const entries = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[data-toc]"));
    expect(entries.map((entry) => entry.getAttribute("href"))).toEqual(CHAPTER_IDS.map((id) => `#${id}`));
    for (const entry of entries) {
      const target = document.getElementById(entry.getAttribute("href")?.slice(1) ?? "");
      expect(target?.dataset.chapter).toBeDefined();
    }
    expect(entries[0].textContent).toBe("01What is an MCP");
    expect(entries[8].textContent).toBe("09Short glossary");
  });

  it.each(["en", "fr"])("opens every external link in a new tab, without opener nor referrer (%s)", (locale) => {
    renderWithIntl(<HomePage />, locale);
    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href^="http"]'));
    expect(new Set(links.map((link) => link.getAttribute("href")))).toEqual(new Set(Object.values(GUIDE_SOURCES)));
    for (const link of links) {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  it("says in French only that the sources are in English", () => {
    renderWithIntl(<HomePage />, "fr");
    expect(document.body.textContent).toContain("(en anglais)");
    renderWithIntl(<HomePage />, "en");
    expect(document.querySelectorAll("[data-guide]")[1].textContent).not.toMatch(/in English/i);
  });

  it("shows the six lamps off and no gauge in the tool zone", () => {
    renderWithIntl(<HomePage />);
    const lamps = toolZone().querySelectorAll("[data-lamp]");
    expect(lamps).toHaveLength(6);
    lamps.forEach((lamp) => expect(lamp.getAttribute("data-state")).toBe("off"));
    expect(toolZone().querySelector("[data-gauge]")).toBeNull();
    expect(toolZone().querySelector("[data-verdict]")).toBeNull();
    expect(toolZone().textContent).toContain("No MCP analyzed");
  });

  it("brings the visitor back to the big field from the end of the guide", () => {
    renderWithIntl(<HomePage />);
    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[data-analyze-link]"));
    expect(links.map((link) => link.textContent)).toEqual(["Analyze an MCP", "ANALYZE AN MCP"]);
    links.forEach((link) => expect(link.getAttribute("href")).toBe(`#${TOOL_ZONE_ID}`));
  });

  it("shows the four verdicts of the legend, the gray one without a needle", () => {
    renderWithIntl(<HomePage />);
    const legend = document.querySelectorAll("[data-verdict-legend]");
    expect(Array.from(legend).map((item) => item.getAttribute("data-verdict-legend"))).toEqual([
      "green",
      "orange",
      "red",
      "gray",
    ]);
    expect(legend[3].querySelector("[data-needle]")).toBeNull();
    expect(legend[2].querySelector("[data-needle]")).not.toBeNull();
  });

  it("names the six lamps with the engine texts", () => {
    renderWithIntl(<HomePage />, "fr");
    const names = Array.from(document.querySelectorAll("[data-lamp-legend] strong")).map((name) => name.textContent);
    expect(names).toEqual([
      "Lit tes fichiers",
      "Modifie tes fichiers",
      "Va sur Internet",
      "Lance des commandes",
      "Touche à tes secrets",
      "Texte caché",
    ]);
  });

  it("gives the dots of the version list a text for screen readers", () => {
    renderWithIntl(<HomePage />);
    const versions = screen.getByRole("list", { name: "The versions of the postmark-mcp package" });
    expect(versions.textContent).toContain("later versions");
    expect(versions.querySelector("[data-trapped-version]")?.textContent).toBe("1.0.16");
  });

  it("has a glossary of eight definitions", () => {
    renderWithIntl(<HomePage />);
    const glossary = document.getElementById("lexique");
    expect(glossary?.querySelectorAll("dl dt")).toHaveLength(8);
    expect(glossary?.querySelectorAll("dl dd")).toHaveLength(8);
  });
});

describe("red example of the guide", () => {
  it("is a real engine report: red, with an R05 alert and the rules version of the current engine", () => {
    const report = parseAnalysisResult(EXAMPLE_REPORT_DATA);
    expect(report).not.toBeNull();
    expect(report?.verdict.color).toBe("red");
    expect(report?.verdict.alerts.map((alert) => alert.rule)).toContain("R05");
    expect(report?.verdict.rules_version).toBe(engineRulesVersion());
  });

  it("reads its color, its lamps and its alert from the report", () => {
    renderWithIntl(<ChapterExample report={exampleReport()} />);
    expect(document.querySelector("[data-verdict]")?.getAttribute("data-verdict")).toBe("red");
    expect(document.querySelector("[data-gauge]")?.getAttribute("data-gauge")).toBe("red");
    expect(document.querySelector("[data-example-alert]")?.getAttribute("data-example-alert")).toBe("R05");
    expect(document.querySelector('[data-lamp="internet"]')?.getAttribute("data-state")).toBe("danger");
  });

  it("follows the report when its color changes, so no color is written in the page", () => {
    const report = exampleReport();
    const orange: AnalysisResult = {
      ...report,
      verdict: { ...report.verdict, color: "orange", alerts: report.verdict.alerts.map((alert) => ({ ...alert, color: "orange" })) },
    };
    renderWithIntl(<ChapterExample report={orange} />);
    expect(document.querySelector("[data-verdict]")?.getAttribute("data-verdict")).toBe("orange");
    expect(document.querySelector('[data-verdict-word="orange"]')?.textContent).toBe("TO CHECK");
    expect(document.querySelector("[data-example-alert]")?.textContent).toContain("TO CHECK");
  });

  it("shows the server name of the report as third-party text", () => {
    renderWithIntl(<ChapterExample report={exampleReport()} />);
    const identity = document.querySelector("[data-example-report] p");
    expect(identity?.querySelector("[data-raw-text]")).not.toBeNull();
    expect(identity?.textContent).toContain("demonstration server");
  });
});

describe("home texts", () => {
  it("have exactly the same home keys in en.json and fr.json", () => {
    expect(homeKeys("fr")).toEqual(homeKeys("en"));
    expect(homeKeys("en").length).toBeGreaterThan(100);
  });
});
