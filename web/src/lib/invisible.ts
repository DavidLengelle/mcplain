import ranges from "./invisible-characters.json";

export type InvisibleCategory = "zero_width" | "bidi_control" | "tag" | "variation_selector" | "control";

export type InvisibleRange = { first: number; last: number; category: InvisibleCategory };

export type TextPiece =
  | { kind: "text"; text: string }
  | { kind: "invisible"; codepoint: number; label: string; category: InvisibleCategory };

function parseCodepoint(text: string): number {
  return Number.parseInt(text.slice(2), 16);
}

export const INVISIBLE_RANGES: InvisibleRange[] = ranges.map((range) => ({
  first: parseCodepoint(range.first),
  last: parseCodepoint(range.last),
  category: range.category as InvisibleCategory,
}));

export function invisibleCategory(codepoint: number): InvisibleCategory | null {
  for (const range of INVISIBLE_RANGES) {
    if (range.first <= codepoint && codepoint <= range.last) {
      return range.category;
    }
  }
  return null;
}

export function codepointLabel(codepoint: number): string {
  return `U+${codepoint.toString(16).toUpperCase().padStart(4, "0")}`;
}

export function splitInvisible(text: string): TextPiece[] {
  const pieces: TextPiece[] = [];
  let current = "";
  for (const character of text) {
    const codepoint = character.codePointAt(0) ?? 0;
    const category = invisibleCategory(codepoint);
    if (category === null) {
      current += character;
      continue;
    }
    if (current !== "") {
      pieces.push({ kind: "text", text: current });
      current = "";
    }
    pieces.push({ kind: "invisible", codepoint, label: codepointLabel(codepoint), category });
  }
  if (current !== "") {
    pieces.push({ kind: "text", text: current });
  }
  return pieces;
}

export function cutText(text: string, limit: number): { text: string; cut: boolean } {
  const characters = Array.from(text);
  if (characters.length <= limit) {
    return { text, cut: false };
  }
  return { text: characters.slice(0, limit).join(""), cut: true };
}
