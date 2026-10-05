import { parseAnalysisView, parseErrorInfo, type AnalysisView } from "./analysis";

export const ANALYSES_PATH = "/api/analyses";
export const INPUT_MAX_CHARACTERS = 500;
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export type StartOutcome =
  | { kind: "accepted"; id: string }
  | { kind: "invalid"; code: string; params: Record<string, string> }
  | { kind: "busy" }
  | { kind: "unavailable" };

export type FetchOutcome =
  | { kind: "found"; analysis: AnalysisView }
  | { kind: "not_found" }
  | { kind: "invalid" }
  | { kind: "unavailable" };

export function isAnalysisId(value: string): boolean {
  return UUID_PATTERN.test(value);
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function startAnalysis(input: string, select: string | null = null): Promise<StartOutcome> {
  const body: { input: string; select?: string } = { input };
  if (select !== null) {
    body.select = select;
  }
  let response: Response;
  try {
    response = await fetch(ANALYSES_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { kind: "unavailable" };
  }
  const data = await readJson(response);
  if (response.status === 202) {
    if (typeof data === "object" && data !== null && "id" in data && typeof data.id === "string") {
      if (isAnalysisId(data.id)) {
        return { kind: "accepted", id: data.id };
      }
    }
    return { kind: "unavailable" };
  }
  if (response.status === 503) {
    return { kind: "busy" };
  }
  if (response.status === 400) {
    const error = parseErrorInfo(data);
    if (error !== null) {
      return { kind: "invalid", code: error.code, params: error.params };
    }
  }
  return { kind: "unavailable" };
}

export async function fetchAnalysis(id: string, signal?: AbortSignal): Promise<FetchOutcome> {
  let response: Response;
  try {
    response = await fetch(`${ANALYSES_PATH}/${id}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
  } catch {
    return { kind: "unavailable" };
  }
  if (response.status === 404) {
    return { kind: "not_found" };
  }
  if (!response.ok) {
    return { kind: "unavailable" };
  }
  const analysis = parseAnalysisView(await readJson(response));
  if (analysis === null || analysis.id !== id) {
    return { kind: "invalid" };
  }
  return { kind: "found", analysis };
}
