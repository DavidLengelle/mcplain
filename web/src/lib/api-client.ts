import type { AiKind } from "./ai-text";
import { parseAnalysisView, parseErrorInfo, type AnalysisView } from "./analysis";

export const ANALYSES_PATH = "/api/analyses";
export const INPUT_MAX_CHARACTERS = 500;
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export const ALTCHA_HEADER = "x-altcha";
export const BURST_LIMIT = "burst_limit";
export const ALTCHA_INVALID = "altcha_invalid";
const SECONDS_PER_MINUTE = 60;

export type StartOutcome =
  | { kind: "accepted"; id: string; cacheOnly: boolean }
  | { kind: "invalid"; code: string; params: Record<string, string> }
  | { kind: "burst"; minutes: number }
  | { kind: "altcha" }
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

function waitMinutes(params: Record<string, string>, retryAfter: string | null): number {
  const minutes = Number.parseInt(params.minutes ?? "", 10);
  if (Number.isInteger(minutes) && minutes > 0) {
    return minutes;
  }
  const seconds = Number.parseInt(retryAfter ?? "", 10);
  if (Number.isInteger(seconds) && seconds > 0) {
    return Math.ceil(seconds / SECONDS_PER_MINUTE);
  }
  return 1;
}

export async function startAnalysis(input: string, select: string | null, altcha: string): Promise<StartOutcome> {
  const body: { input: string; select?: string } = { input };
  if (select !== null) {
    body.select = select;
  }
  let response: Response;
  try {
    response = await fetch(ANALYSES_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", [ALTCHA_HEADER]: altcha },
      body: JSON.stringify(body),
    });
  } catch {
    return { kind: "unavailable" };
  }
  const data = await readJson(response);
  if (response.status === 202) {
    if (typeof data === "object" && data !== null && "id" in data && typeof data.id === "string") {
      if (isAnalysisId(data.id)) {
        return { kind: "accepted", id: data.id, cacheOnly: "cache_only" in data && data.cache_only === true };
      }
    }
    return { kind: "unavailable" };
  }
  const refusal = parseErrorInfo(data);
  if (response.status === 429 && refusal?.code === BURST_LIMIT) {
    return { kind: "burst", minutes: waitMinutes(refusal.params, response.headers.get("Retry-After")) };
  }
  if (response.status === 403 && refusal?.code === ALTCHA_INVALID) {
    return { kind: "altcha" };
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

export async function askAiText(id: string, kind: AiKind, lang: string, signal?: AbortSignal): Promise<unknown> {
  try {
    const response = await fetch(`${ANALYSES_PATH}/${id}/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ lang }),
      signal,
    });
    if (!response.ok) {
      return null;
    }
    return await readJson(response);
  } catch {
    return null;
  }
}

export async function readAiText(id: string, kind: AiKind, lang: string, signal?: AbortSignal): Promise<unknown> {
  try {
    const response = await fetch(`${ANALYSES_PATH}/${id}/${kind}?lang=${encodeURIComponent(lang)}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    if (!response.ok) {
      return null;
    }
    return await readJson(response);
  } catch {
    return null;
  }
}
