import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { THEME_CLASSES, THEME_STORAGE_KEY } from "@/lib/theme";

type Tokens = Record<string, string>;
type Pair = { text: string; background: string; minimum: number };

const CSS = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf-8");
const SCRIPT = readFileSync(join(process.cwd(), "public", "theme.js"), "utf-8");
const DECLARATION = /^\s*(--[\w-]+):\s*([^;]+);/gm;
const BODY = 4.5;
const LARGE = 3;
const BRIGHT_ORANGE = "#E8892E";
const COPPER = "#C77B30";
const VALIDATED_EXCEPTION = { theme: "light", text: "--warn", background: "--panel", minimum: 2.1 };

const PAIRS: Pair[] = [
  { text: "--ink", background: "--page", minimum: BODY },
  { text: "--ink", background: "--panel", minimum: BODY },
  { text: "--ink", background: "--panel2", minimum: BODY },
  { text: "--ink2", background: "--panel", minimum: BODY },
  { text: "--ink2", background: "--panel2", minimum: BODY },
  { text: "--ink3", background: "--panel2", minimum: BODY },
  { text: "--muted", background: "--page", minimum: BODY },
  { text: "--muted", background: "--panel", minimum: BODY },
  { text: "--muted", background: "--panel2", minimum: BODY },
  { text: "--muted", background: "--card-hover", minimum: BODY },
  { text: "--muted", background: "--input-bg", minimum: BODY },
  { text: "--faint", background: "--page", minimum: BODY },
  { text: "--faint", background: "--panel", minimum: BODY },
  { text: "--faint", background: "--panel2", minimum: BODY },
  { text: "--accent", background: "--page", minimum: BODY },
  { text: "--accent", background: "--panel", minimum: BODY },
  { text: "--on-accent", background: "--accent", minimum: BODY },
  { text: "--warn-text", background: "--page", minimum: BODY },
  { text: "--warn-text", background: "--panel", minimum: BODY },
  { text: "--warn-text", background: "--warn-note", minimum: BODY },
  { text: "--red", background: "--page", minimum: BODY },
  { text: "--red", background: "--panel", minimum: BODY },
  { text: "--red", background: "--red-note", minimum: BODY },
  { text: "--ink", background: "--warn-note", minimum: BODY },
  { text: "--ink", background: "--red-note", minimum: BODY },
  { text: "--green", background: "--panel", minimum: LARGE },
  { text: "--warn", background: "--panel", minimum: LARGE },
  { text: "--red", background: "--panel", minimum: LARGE },
  { text: "--gray", background: "--panel", minimum: LARGE },
  { text: "--cluster-ink", background: "--cluster-bg", minimum: BODY },
  { text: "--cluster-ink2", background: "--cluster-bg", minimum: BODY },
  { text: "--cluster-muted", background: "--cluster-bg", minimum: BODY },
  { text: "--lamp-on-text", background: "--cluster-bg", minimum: BODY },
  { text: "--lamp-off-text", background: "--cluster-bg", minimum: BODY },
  { text: "--lamp-danger-text", background: "--cluster-bg", minimum: BODY },
  { text: "--chip-label", background: "--panel", minimum: BODY },
  { text: "--chip-danger", background: "--panel", minimum: BODY },
  { text: "--toggle-fg", background: "--toggle-bg", minimum: BODY },
  { text: "--toggle-on-fg", background: "--toggle-on-bg", minimum: BODY },
  { text: "--orig-fg", background: "--orig-bg", minimum: BODY },
  { text: "--ink", background: "--code-bg", minimum: BODY },
  { text: "--ink", background: "--input-bg", minimum: BODY },
  { text: "--ink", background: "--row-hover", minimum: BODY },
  { text: "--ink", background: "--card-hover", minimum: BODY },
];

function tokens(block: string): Tokens {
  return Object.fromEntries(Array.from(block.matchAll(DECLARATION), (match) => [match[1], match[2].trim()]));
}

function themes(): { light: Tokens; dark: Tokens } {
  const root = CSS.slice(CSS.indexOf(":root {"));
  const variant = root.indexOf("@variant dark {");
  const end = root.indexOf("}", variant);
  const light = tokens(root.slice(0, variant));
  const dark = { ...light, ...tokens(root.slice(variant, end)) };
  return { light, dark };
}

function channel(value: number): number {
  const scaled = value / 255;
  if (scaled <= 0.03928) {
    return scaled / 12.92;
  }
  return ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const [red, green, blue] = [0, 2, 4].map((start) => channel(Number.parseInt(value.slice(start, start + 2), 16)));
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(first: string, second: string): number {
  const [high, low] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (high + 0.05) / (low + 0.05);
}

function background(theme: Tokens, name: string): string {
  const value = theme[name];
  if (value === "transparent") {
    return theme["--panel"];
  }
  return value;
}

describe("theme tokens", () => {
  const { light, dark } = themes();

  it("defines the same tokens, all colors written in full, in both themes", () => {
    expect(Object.keys(light).length).toBeGreaterThan(60);
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
    expect(light["--page"]).toBe("#F5F7FA");
    expect(dark["--page"]).toBe("#0C131B");
  });

  it("computes contrast like WCAG", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#777777")).toBe(1);
  });

  for (const [name, theme] of [
    ["light", light],
    ["dark", dark],
  ] as const) {
    it(`keeps every main text readable in the ${name} theme`, () => {
      const failures: string[] = [];
      for (const pair of PAIRS) {
        const ratio = contrast(theme[pair.text], background(theme, pair.background));
        let minimum = pair.minimum;
        const exception =
          name === VALIDATED_EXCEPTION.theme &&
          pair.text === VALIDATED_EXCEPTION.text &&
          pair.background === VALIDATED_EXCEPTION.background;
        if (exception) {
          minimum = VALIDATED_EXCEPTION.minimum;
        }
        if (ratio < minimum) {
          failures.push(`${pair.text} on ${pair.background}: ${ratio.toFixed(2)}`);
        }
      }
      expect(failures).toEqual([]);
    });
  }

  it("documents the only exception: the big orange word of the light theme is under 3:1", () => {
    expect(light["--warn"]).toBe(BRIGHT_ORANGE);
    expect(contrast(light["--warn"], light["--panel"])).toBeLessThan(LARGE);
    expect(light["--warn-text"]).not.toBe(BRIGHT_ORANGE);
  });

  it("never uses the bright orange in the dark theme, where orange stays copper", () => {
    expect(dark["--warn"]).toBe(COPPER);
    expect(dark["--warn-text"]).toBe(COPPER);
    const darkBlock = CSS.slice(CSS.indexOf("@variant dark {"));
    expect(darkBlock.slice(0, darkBlock.indexOf("}")).toUpperCase()).not.toContain(BRIGHT_ORANGE);
  });

  it("follows the system without JavaScript, and lets th-light and th-dark win", () => {
    expect(CSS).toContain("@media (prefers-color-scheme: dark)");
    expect(CSS).toContain(":not(.th-light, .th-light *)");
    expect(CSS).toContain(".th-dark");
  });

  it("uses the same storage key and classes in the theme script and in the switcher", () => {
    expect(SCRIPT).toContain(`"${THEME_STORAGE_KEY}"`);
    expect(SCRIPT).toContain('"th-" + choice');
    expect(THEME_CLASSES).toEqual({ light: "th-light", dark: "th-dark" });
    expect(SCRIPT).not.toMatch(/document\.cookie/);
  });
});
