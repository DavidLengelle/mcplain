import type { Page, Route } from "@playwright/test";

export const ID = "5b0c6f2e-8d3a-4c1b-9e7f-0a1b2c3d4e5f";
export const SECOND_ID = "9c8b7a65-4321-4fed-8cba-987654321000";

type Json = Record<string, unknown>;

export function view(state: string, body: Json | null, extra: Json = {}): Json {
  let finished: string | null = null;
  if (state === "done" || state === "failed") {
    finished = "2026-10-05T10:00:05+00:00";
  }
  return {
    id: ID,
    input: "uvx weather-demo",
    select: null,
    state,
    created_at: "2026-10-05T10:00:00+00:00",
    finished_at: finished,
    analyzed_at: finished,
    from_cache: false,
    result: body,
    error_code: null,
    ...extra,
  };
}

export async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function serveAnalysis(page: Page, answers: Json[], id: string = ID): Promise<string[]> {
  const seen: string[] = [];
  let index = 0;
  await page.route(`**/api/analyses/${id}`, async (route) => {
    seen.push(route.request().method());
    const answer = answers[Math.min(index, answers.length - 1)];
    index += 1;
    await fulfill(route, 200, answer);
  });
  return seen;
}
