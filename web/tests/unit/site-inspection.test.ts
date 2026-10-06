import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const SOURCE_FOLDER = join(process.cwd(), "src");
const PUBLIC_FOLDER = join(process.cwd(), "public");
const TEXT_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".css"]);
const FORBIDDEN: { name: string; pattern: RegExp }[] = [
  { name: "dangerouslySetInnerHTML", pattern: /dangerouslySetInnerHTML/ },
  { name: "innerHTML", pattern: /\b(innerHTML|outerHTML|insertAdjacentHTML)\b/ },
  { name: "use server", pattern: /["'`]use server["'`]/ },
  { name: "eval", pattern: /(?<!'unsafe-)\beval\b/ },
  { name: "new Function", pattern: /\bnew\s+Function\s*\(/ },
];

function sourceFiles(folder: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) {
      files.push(...sourceFiles(path));
    } else if (TEXT_EXTENSIONS.has(extname(entry.name))) {
      files.push(path);
    }
  }
  return files;
}

function violations(text: string): string[] {
  return FORBIDDEN.filter((rule) => rule.pattern.test(text)).map((rule) => rule.name);
}

describe("technical inspection of the site", () => {
  it("finds every forbidden construction in a sample", () => {
    expect(violations("<div dangerouslySetInnerHTML={{ __html: text }} />")).toContain("dangerouslySetInnerHTML");
    expect(violations("node.innerHTML = text")).toEqual(["innerHTML"]);
    expect(violations("node.insertAdjacentHTML('beforeend', text)")).toEqual(["innerHTML"]);
    expect(violations('"use server";')).toEqual(["use server"]);
    expect(violations("'use server'")).toEqual(["use server"]);
    expect(violations("window.eval(text)")).toEqual(["eval"]);
    expect(violations("new Function(text)")).toEqual(["new Function"]);
    expect(violations("retrieval and evaluation")).toEqual([]);
    expect(violations("script-src 'unsafe-eval'")).toEqual([]);
    expect(violations("unsafe-eval(text)")).toEqual(["eval"]);
  });

  it("keeps next dev from writing AGENTS.md and CLAUDE.md", () => {
    const config = readFileSync(join(process.cwd(), "next.config.ts"), "utf-8");
    expect(config).toMatch(/^\s*agentRules:\s*false,\s*$/m);
  });

  it("finds none of them in src/ and public/", () => {
    const files = [...sourceFiles(SOURCE_FOLDER), ...sourceFiles(PUBLIC_FOLDER)];
    expect(files.length).toBeGreaterThan(0);
    const found = files.flatMap((path) =>
      violations(readFileSync(path, "utf-8")).map((name) => `${relative(SOURCE_FOLDER, path)}: ${name}`),
    );
    expect(found).toEqual([]);
  });
});
