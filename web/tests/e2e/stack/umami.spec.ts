import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

import { psql } from "./helpers";

function umamiSql(statement: string): string {
  return execFileSync("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "mcplain", "-d", "umami", "-At", "-c", statement], {
    encoding: "utf-8",
  }).trim();
}

function count(statement: string): number {
  return Number.parseInt(umamiSql(statement), 10);
}

test.beforeEach(async ({ request }) => {
  const script = await request.get("/umami/script.js");
  test.skip(script.status() !== 200, "Umami is not set up on this stack (run scripts/umami-first-setup.sh)");
});

test("the real Umami counts a report with its path cleaned, and nothing from the admin page, without cookie nor storage", async ({ page, context }) => {
  const analysis = psql("SELECT id FROM analyses WHERE state = 'done' ORDER BY created_at DESC LIMIT 1;").trim();
  test.skip(analysis === "", "no finished analysis on this stack");
  const since = umamiSql("SELECT now()::text;");
  const answers: number[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname === "/umami/api/send") {
      answers.push(response.status());
    }
  });
  await page.goto(`/fr/analyses/${analysis}?from=a-secret-link`);
  await expect(page.locator("[data-report]")).toBeVisible({ timeout: 60_000 });
  await expect
    .poll(() => count(`SELECT count(*) FROM website_event WHERE created_at >= '${since}' AND url_path = '/fr/analyses/[id]';`), { timeout: 20_000 })
    .toBe(1);
  expect(count(`SELECT count(*) FROM website_event WHERE created_at >= '${since}' AND (url_path LIKE '%${analysis}%' OR url_query <> '' OR coalesce(referrer_path, '') LIKE '%${analysis}%');`)).toBe(0);
  await page.goto("/fr/admin");
  await page.goto("/account");
  await page.waitForTimeout(3000);
  expect(count(`SELECT count(*) FROM website_event WHERE created_at >= '${since}' AND (url_path LIKE '%admin%' OR url_path LIKE '%account%');`)).toBe(0);
  expect(answers).toEqual([200]);
  const cookies = (await context.cookies()).map((cookie) => cookie.name);
  expect(cookies.filter((name) => name !== "NEXT_LOCALE")).toEqual([]);
  expect(cookies.filter((name) => name.toLowerCase().includes("umami"))).toEqual([]);
  expect(await page.evaluate(() => [window.localStorage.length, window.sessionStorage.length])).toEqual([0, 0]);
});

test("the dashboard of Umami is never reached through the website", async ({ request }) => {
  for (const path of ["/umami", "/umami/login", "/umami/api/auth/login", "/umami/api/websites", "/umami/api/me", "/umami/api/heartbeat"]) {
    expect((await request.get(path)).status(), path).toBe(404);
    expect((await request.post(path, { data: { username: "admin", password: "umami" } })).status(), path).toBe(404);
  }
});
