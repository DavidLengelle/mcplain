import { readFileSync } from "node:fs";
import { join } from "node:path";

import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";

type Tree = { [key: string]: string | Tree };

function load(language: string): Tree {
  return JSON.parse(readFileSync(join(process.cwd(), "messages", `${language}.json`), "utf-8"));
}

function leaves(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = `${prefix}${key}`;
    if (typeof value === "string") {
      return [[path, value] as [string, string]];
    }
    return leaves(value, `${path}.`);
  });
}

describe("interface messages", () => {
  const english = load("en");
  const french = load("fr");

  it("have exactly the same keys in en.json and fr.json", () => {
    const englishKeys = leaves(english).map(([key]) => key).sort();
    const frenchKeys = leaves(french).map(([key]) => key).sort();
    expect(frenchKeys).toEqual(englishKeys);
  });

  it("never use the engine namespace, which holds the engine texts", () => {
    expect(english.engine).toBeUndefined();
    expect(french.engine).toBeUndefined();
  });

  it.each([
    ["en", english],
    ["fr", french],
  ])("are valid ICU messages in %s", (locale, tree) => {
    const t = createTranslator({
      locale,
      messages: tree,
      onError: (error) => {
        throw error;
      },
    });
    for (const [key, message] of leaves(tree)) {
      const values: Record<string, string> = {};
      for (const match of message.matchAll(/\{(\w+)/g)) {
        values[match[1]] = "1";
      }
      expect(() => t(key as never, values as never), key).not.toThrow();
    }
  });
});
