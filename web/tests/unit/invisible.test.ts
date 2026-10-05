import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { INVISIBLE_RANGES, invisibleCategory, splitInvisible } from "@/lib/invisible";

const ENGINE_SOURCE = join(process.cwd(), "..", "engine", "src", "mcplain", "adapters", "common.py");
const ENGINE_RANGE = /\((0x[0-9A-Fa-f]+), (0x[0-9A-Fa-f]+), InvisibleCategory\.([A-Z_]+)\)/g;

function engineRanges(): { first: number; last: number; category: string }[] {
  const source = readFileSync(ENGINE_SOURCE, "utf-8");
  const block = source.slice(source.indexOf("INVISIBLE_RANGES"), source.indexOf("INVISIBLE_PATTERN"));
  return Array.from(block.matchAll(ENGINE_RANGE), (match) => ({
    first: Number.parseInt(match[1], 16),
    last: Number.parseInt(match[2], 16),
    category: match[3].toLowerCase(),
  }));
}

describe("invisible characters", () => {
  it("are exactly the ranges of the engine, read from its source", () => {
    const ranges = engineRanges();
    expect(ranges.length).toBeGreaterThan(10);
    expect(INVISIBLE_RANGES).toEqual(ranges);
  });

  it("include the bidi controls and the whole Unicode Tags block", () => {
    for (const codepoint of [0x202a, 0x202e, 0x2066, 0x2069, 0x200e, 0x200f, 0x061c]) {
      expect(invisibleCategory(codepoint)).toBe("bidi_control");
    }
    for (let codepoint = 0xe0000; codepoint <= 0xe007f; codepoint += 1) {
      expect(invisibleCategory(codepoint)).toBe("tag");
    }
  });

  it("turn the first and the last character of every range into a badge, and nothing around them", () => {
    for (const range of INVISIBLE_RANGES) {
      for (const codepoint of [range.first, range.last]) {
        const pieces = splitInvisible(`a${String.fromCodePoint(codepoint)}b`);
        expect(pieces.map((piece) => piece.kind)).toEqual(["text", "invisible", "text"]);
      }
    }
    for (const text of ["a", "é", "\n", "\t", "日本", "\u{1F600}"]) {
      expect(splitInvisible(text)).toEqual([{ kind: "text", text }]);
    }
  });
});
