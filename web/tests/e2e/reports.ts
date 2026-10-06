import { readFileSync } from "node:fs";
import { join } from "node:path";

import { ID } from "./fake-api";

type Json = Record<string, unknown>;

const FIXTURES = join(__dirname, "..", "fixtures");
const ANALYZED_AT = "2026-10-06T09:30:00+00:00";

export const REPORTS = {
  orange: "server-filesystem.view",
  green: "mcp-server-time.view",
  red: "postmark-like.result",
  greenDomains: "fixed-domains.result",
  go: "github-mcp-server.view",
  failed: "npm-not-found.view",
  multiple: "modelcontextprotocol-servers.view",
  awesome: "awesome-mcp-servers.view",
} as const;

export type ReportName = keyof typeof REPORTS;

function readFixture(file: string): Json {
  return JSON.parse(readFileSync(join(FIXTURES, `${file}.json`), "utf-8")) as Json;
}

export function reportView(name: ReportName, id: string = ID): Json {
  const file = REPORTS[name];
  const data = readFixture(file);
  if (file.endsWith(".view")) {
    return { ...data, id };
  }
  return {
    id,
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
