import { describe, expect, it } from "vitest";

import { parseAnalysisView } from "@/lib/analysis";

const ID = "8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";

function result(color: string, status = "ok"): Record<string, unknown> {
  return { status, verdict: { color, alerts: [], reasons: [] }, servers: [] };
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

  it.each([
    ["an unknown state", view("paused", null)],
    ["a finished analysis without a result", view("done", null)],
    ["an unknown color", view("done", result("blue"))],
    ["a failed analysis that is not gray", view("failed", result("green"))],
    ["a reason that is not a message key", view("done", { ...result("gray"), verdict: { color: "gray", reasons: ["a b"] } })],
    ["an alert without a rule", view("done", { ...result("red"), verdict: { color: "red", alerts: [{ color: "red" }] } })],
    ["text instead of an object", "done"],
    ["nothing", null],
  ])("refuses %s", (_name, value) => {
    expect(parseAnalysisView(value)).toBeNull();
  });
});
