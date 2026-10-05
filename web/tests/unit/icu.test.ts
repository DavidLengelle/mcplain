import { readFileSync } from "node:fs";
import { join } from "node:path";

import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";

import { engineCatalogToMessages, pythonToIcu, type MessageTree } from "@/lib/icu";

const ENGINE_LOCALES = join(process.cwd(), "..", "engine", "src", "mcplain", "locales");
const PYTHON_FIELD = /\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

function format(message: string, values: Record<string, string> = {}): string {
  const t = createTranslator({
    locale: "en",
    messages: { message },
    onError: (error) => {
      throw error;
    },
  });
  return t("message", values);
}

function pythonFormat(template: string, values: Record<string, string>): string {
  return template.replace(PYTHON_FIELD, (match: string, field: string | undefined) => {
    if (field === undefined) {
      return match[0];
    }
    return values[field];
  });
}

function fieldValues(template: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const match of template.matchAll(PYTHON_FIELD)) {
    if (match[1] !== undefined) {
      values[match[1]] = `<${match[1]} '{x}'>`;
    }
  }
  return values;
}

function lookup(tree: MessageTree, key: string): string | MessageTree | undefined {
  let node: string | MessageTree | undefined = tree;
  for (const segment of key.split(".")) {
    if (typeof node !== "object") {
      return undefined;
    }
    node = node[segment];
  }
  return node;
}

function engineCatalog(language: string): Record<string, string> {
  return JSON.parse(readFileSync(join(ENGINE_LOCALES, `${language}.json`), "utf-8"));
}

describe("pythonToIcu", () => {
  const cases: [string, Record<string, string>, string][] = [
    ["Hello {name}", { name: "Ada" }, "Hello Ada"],
    ["l'{name} d'abord", { name: "outil" }, "l'outil d'abord"],
    ["l'outil", {}, "l'outil"],
    ["{{literal}} and }}", {}, "{literal} and }"],
    ["<script>alert(1)</script>", {}, "<script>alert(1)</script>"],
    ["'{{x}}' <'> {{'}}", {}, "'{x}' <'> {'}"],
    ["a # b | c", {}, "a # b | c"],
    ["{count} file(s)", { count: "2" }, "2 file(s)"],
  ];

  it.each(cases)("formats %j like Python", (template, values, expected) => {
    const message = pythonToIcu(template);
    expect(message).not.toBeNull();
    expect(format(message ?? "", values)).toBe(expected);
  });

  it("refuses what Python format would refuse or what is not a plain name", () => {
    expect(pythonToIcu("a } b")).toBeNull();
    expect(pythonToIcu("a { b")).toBeNull();
    expect(pythonToIcu("{0}")).toBeNull();
    expect(pythonToIcu("{name!r}")).toBeNull();
    expect(pythonToIcu("{name:>10}")).toBeNull();
  });

  it("keeps any literal text intact, whatever its special characters", () => {
    const alphabet = ["a", " ", "'", "{", "}", "<", ">", "#", "|", "é", "/"];
    let seed = 42;
    function random(limit: number): number {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % limit;
    }
    for (let round = 0; round < 2000; round += 1) {
      const pieces: string[] = [];
      for (let index = 0; index < 1 + random(4); index += 1) {
        let piece = "";
        for (let length = 0; length < random(8); length += 1) {
          piece += alphabet[random(alphabet.length)];
        }
        pieces.push(piece);
      }
      const values: Record<string, string> = {};
      let template = "";
      let expected = "";
      pieces.forEach((piece, index) => {
        template += piece.replaceAll("{", "{{").replaceAll("}", "}}");
        expected += piece;
        if (index < pieces.length - 1) {
          const name = `v${index}`;
          values[name] = `'{${index}}'`;
          template += `{${name}}`;
          expected += values[name];
        }
      });
      const message = pythonToIcu(template);
      expect(message, template).not.toBeNull();
      expect(format(message ?? "", values), template).toBe(expected);
    }
  });
});

describe("engineCatalogToMessages", () => {
  it("nests dotted keys, the way next-intl reads them", () => {
    expect(engineCatalogToMessages({ "rule.R01.title": "Invisible text", "status.ok": "done" })).toEqual({
      rule: { R01: { title: "Invisible text" } },
      status: { ok: "done" },
    });
  });

  it("drops keys and values that cannot be used safely", () => {
    const tree = engineCatalogToMessages({
      "a.b": "kept",
      "a.b.c": "branch under a leaf",
      "__proto__.polluted": "no",
      "x.constructor": "no",
      "bad key": "no",
      "number.value": 3,
      "broken.brace": "a } b",
    });
    expect(tree).toEqual({ a: { b: "kept" } });
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it("refuses anything that is not a catalog", () => {
    expect(engineCatalogToMessages(null)).toBeNull();
    expect(engineCatalogToMessages(["a"])).toBeNull();
    expect(engineCatalogToMessages("text")).toBeNull();
    expect(engineCatalogToMessages({})).toBeNull();
  });

  it.each(["en", "fr"])("gives every engine text in %s exactly as Python would", (language) => {
    const catalog = engineCatalog(language);
    const tree = engineCatalogToMessages(catalog);
    expect(tree).not.toBeNull();
    const keys = Object.keys(catalog);
    expect(keys.length).toBeGreaterThan(300);
    for (const key of keys) {
      const template = catalog[key];
      const message = lookup(tree ?? {}, key);
      expect(typeof message, key).toBe("string");
      const values = fieldValues(template);
      expect(format(message as string, values), key).toBe(pythonFormat(template, values));
    }
  });
});
