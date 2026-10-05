import { describe, expect, it } from "vitest";

import { VerdictPanel } from "@/components/report/verdict-panel";
import { VerdictBadge } from "@/components/verdict-badge";
import { VERDICT_COLORS } from "@/lib/analysis";

import { renderWithIntl } from "./intl";

const WORDS: Record<string, Record<string, string>> = {
  en: { red: "Red", orange: "Orange", green: "Green", gray: "Gray" },
  fr: { red: "Rouge", orange: "Orange", green: "Vert", gray: "Gris" },
};

describe("verdict badge", () => {
  it.each(["en", "fr"])("has a word and an icon for each color in %s", (locale) => {
    const icons = new Set<string>();
    for (const color of VERDICT_COLORS) {
      const { container, unmount } = renderWithIntl(<VerdictBadge color={color} />, locale);
      const badge = container.querySelector(`[data-verdict="${color}"]`);
      expect(badge?.textContent?.trim()).toBe(WORDS[locale][color]);
      const icon = badge?.querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon?.getAttribute("aria-hidden")).toBe("true");
      icons.add(icon?.getAttribute("class") ?? "");
      unmount();
    }
    expect(icons.size).toBe(VERDICT_COLORS.length);
  });

  it.each([
    ["en", "That does not mean it is safe."],
    ["fr", "Ça ne veut pas dire qu'il est sûr."],
  ])("always says that gray is not safe, in %s", (locale, sentence) => {
    const { container } = renderWithIntl(<VerdictPanel color="gray" />, locale);
    expect(container.textContent).toContain(sentence);
  });

  it("does not add that sentence to the other colors", () => {
    for (const color of ["red", "orange", "green"] as const) {
      const { container, unmount } = renderWithIntl(<VerdictPanel color={color} />);
      expect(container.textContent).not.toContain("That does not mean it is safe.");
      unmount();
    }
  });
});
