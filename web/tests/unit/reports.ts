import { readFileSync } from "node:fs";
import { join } from "node:path";

import { parseAnalysisView, type AnalysisView } from "@/lib/analysis";

type Json = Record<string, unknown>;

export const VIEW_ID = "5b0c6f2e-8d3a-4c1b-9e7f-0a1b2c3d4e5f";
const ANALYZED_AT = "2026-10-06T09:30:00+00:00";

export function fixtureJson(file: string): Json {
  return JSON.parse(readFileSync(join(process.cwd(), "tests", "fixtures", `${file}.json`), "utf-8")) as Json;
}

export function rawView(file: string): Json {
  const data = fixtureJson(file);
  if (file.endsWith(".view")) {
    return { ...data, id: VIEW_ID };
  }
  return {
    id: VIEW_ID,
    input: "npx -y demo-fixture",
    select: null,
    state: "done",
    created_at: ANALYZED_AT,
    finished_at: ANALYZED_AT,
    analyzed_at: ANALYZED_AT,
    from_cache: false,
    error_code: null,
    result: data,
  };
}

export function loadView(file: string): AnalysisView {
  const parsed = parseAnalysisView(rawView(file));
  if (parsed === null) {
    throw new Error(`fixture ${file} does not parse`);
  }
  return parsed;
}
