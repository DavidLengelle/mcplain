import { describe, expect, it } from "vitest";

import { parseAnalysisView } from "@/lib/analysis";

const ID = "8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";

function result(color: string, status = "ok"): Record<string, unknown> {
  return { status, verdict: { color, alerts: [], reasons: [] }, servers: [] };
}

function coverage(items: Record<string, unknown>[]): Record<string, unknown> {
  return { tools_total: 1, tools_followed: 0, files_total: 1, files_read: 1, not_checked: items };
}

function view(state: string, body: Record<string, unknown> | null): Record<string, unknown> {
  return { id: ID, input: "uvx mcp-server-fetch", select: null, state, result: body, error_code: null };
}

describe("parseAnalysisView", () => {
  it("accepts a running analysis without a result", () => {
    expect(parseAnalysisView(view("fetching", null))?.state).toBe("fetching");
  });

  it("keeps the color given by the engine", () => {
    expect(parseAnalysisView(view("done", result("orange")))?.result?.verdict.color).toBe("orange");
    expect(parseAnalysisView(view("done", result("red", "compiled")))?.result?.verdict.color).toBe("red");
  });

  it("reads the coverage of a partial gray, or nothing when there is none", () => {
    const item = { kind: "network", reason: "network_unresolved", name: "httpx", file: "a.py", line: 1 };
    const body = { ...result("gray"), verdict: { color: "gray", coverage: coverage([item]) } };
    const parsed = parseAnalysisView(view("done", body))?.result?.verdict.coverage;
    expect(parsed?.not_checked).toEqual([{ ...item, snippet: null }]);
    expect(parsed?.not_checked_count).toBe(0);
    expect(parseAnalysisView(view("done", result("green")))?.result?.verdict.coverage).toBeNull();
  });

  it.each([
    ["an unknown state", view("paused", null)],
    ["a finished analysis without a result", view("done", null)],
    ["an unknown color", view("done", result("blue"))],
    ["a failed analysis that is not gray", view("failed", result("green"))],
    ["a reason that is not a message key", view("done", { ...result("gray"), verdict: { color: "gray", reasons: ["a b"] } })],
    ["an alert without a rule", view("done", { ...result("red"), verdict: { color: "red", alerts: [{ color: "red" }] } })],
    [
      "a coverage item of an unknown kind",
      view("done", { ...result("gray"), verdict: { color: "gray", coverage: coverage([{ kind: "cache", reason: "x" }]) } }),
    ],
    [
      "a coverage item whose reason is not a message key",
      view("done", { ...result("gray"), verdict: { color: "gray", coverage: coverage([{ kind: "file", reason: "a b" }]) } }),
    ],
    ["text instead of an object", "done"],
    ["nothing", null],
  ])("refuses %s", (_name, value) => {
    expect(parseAnalysisView(value)).toBeNull();
  });
});
