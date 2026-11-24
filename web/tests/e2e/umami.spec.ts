import { randomUUID } from "node:crypto";

import type { APIRequestContext, Browser, BrowserContext, Page } from "@playwright/test";

import { expect, test } from "./test";

import { fulfill, ID, serveAnalysis } from "./fake-api";
import { TEST_WEBSITE_ID, UMAMI_RECORDS } from "../../playwright.config";
import { reportView } from "./reports";

const QUIET_MILLISECONDS = 2500;
const CHALLENGE = { algorithm: "PBKDF2/SHA-256" };

type Recorded = { headers: { [name: string]: string }; body: { type: string; payload: { [name: string]: unknown } } };

async function visitor(browser: Browser, init?: string): Promise<{ context: BrowserContext; page: Page; agent: string; sent: string[] }> {
  const agent = `mcplain-e2e-${randomUUID()}`;
  const context = await browser.newContext({ userAgent: agent, locale: "fr-FR" });
  if (init !== undefined) {
    await context.addInitScript(init);
  }
  const page = await context.newPage();
  await page.route("**/api/altcha/challenge", async (route) => {
    await fulfill(route, 200, CHALLENGE);
  });
  await page.route("**/api/quota", async (route) => {
    await fulfill(route, 404, { error: { code: "api.not_found", params: {} } });
  });
  const sent: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/umami/api/")) {
      sent.push(request.url());
    }
  });
  return { context, page, agent, sent };
}

async function records(request: APIRequestContext, agent: string): Promise<Recorded[]> {
  const answer = await request.get(`${UMAMI_RECORDS}?${new URLSearchParams({ agent }).toString()}`);
  return (await answer.json()) as Recorded[];
}

async function storage(page: Page): Promise<number[]> {
  return page.evaluate(() => [window.localStorage.length, window.sessionStorage.length]);
}

test("a report page is counted with its path cleaned, without the query, and leaves no cookie nor storage", async ({ browser, request }) => {
  const { context, page, agent } = await visitor(browser);
  await serveAnalysis(page, [reportView("orange")]);
  await page.goto(`/fr/analyses/${ID}?from=secret-link#tool-1`);
  await expect(page.locator("[data-report]")).toBeVisible();
  await expect.poll(async () => (await records(request, agent)).length, { timeout: 10_000 }).toBeGreaterThan(0);
  const [first] = await records(request, agent);
  expect(first?.body.type).toBe("event");
  expect(first?.body.payload.url).toBe("/fr/analyses/[id]");
  expect(first?.body.payload.website).toBe(TEST_WEBSITE_ID);
  expect(JSON.stringify(first?.body)).not.toContain(ID);
  expect(JSON.stringify(first?.body)).not.toContain("secret-link");
  expect(first?.headers["x-mcplain-visitor-ip"]).toBe("127.0.0.1");
  expect(first?.headers.cookie).toBeUndefined();
  expect(await context.cookies()).toEqual([]);
  expect(await storage(page)).toEqual([0, 0]);
  const tag = page.locator('script[src="/umami/script.js"]');
  await expect(tag).toHaveAttribute("data-website-id", TEST_WEBSITE_ID);
  await expect(tag).toHaveAttribute("data-do-not-track", "true");
  await expect(tag).toHaveAttribute("data-host-url", "/umami");
  await context.close();
});

test("a move inside the site is counted with the previous page cleaned as referrer", async ({ browser, request }) => {
  const { context, page, agent } = await visitor(browser);
  await page.goto("/fr");
  await expect.poll(async () => (await records(request, agent)).length, { timeout: 10_000 }).toBe(1);
  await page.locator('footer a[href="/fr/privacy"]').click();
  await expect(page.locator("[data-privacy]")).toBeVisible();
  await expect.poll(async () => (await records(request, agent)).length, { timeout: 10_000 }).toBe(2);
  const second = (await records(request, agent))[1];
  expect(second?.body.payload.url).toBe("/fr/privacy");
  expect(second?.body.payload.referrer).toBe("/fr");
  expect(await context.cookies()).toEqual([]);
  await context.close();
});

test("nothing is sent from the admin page nor from the account pages, even after a visit of the site", async ({ browser, request }) => {
  const { context, page, agent, sent } = await visitor(browser);
  await page.goto("/fr");
  await expect.poll(async () => (await records(request, agent)).length, { timeout: 10_000 }).toBe(1);
  const before = sent.length;
  for (const path of ["/fr/admin", "/admin", "/fr/account/sign-in", "/account"]) {
    await page.goto(path);
    await page.waitForTimeout(QUIET_MILLISECONDS / 2);
  }
  expect(sent.length).toBe(before);
  expect((await records(request, agent)).map((record) => record.body.payload.url)).toEqual(["/fr"]);
  await context.close();
});

for (const [signal, init] of [
  ["Do Not Track", "Object.defineProperty(navigator, 'doNotTrack', { get: () => '1' });"],
  ["Global Privacy Control", "Object.defineProperty(navigator, 'globalPrivacyControl', { get: () => true });"],
] as const) {
  test(`nothing is sent with ${signal}`, async ({ browser, request }) => {
    const { context, page, agent, sent } = await visitor(browser, init);
    await serveAnalysis(page, [reportView("green")]);
    await page.goto(`/fr/analyses/${ID}`);
    await expect(page.locator("[data-report]")).toBeVisible();
    await page.waitForTimeout(QUIET_MILLISECONDS);
    expect(sent).toEqual([]);
    expect(await records(request, agent)).toEqual([]);
    await context.close();
  });
}

test("only the two paths of Umami pass the relay; anything else under /umami is 404", async ({ request }) => {
  expect((await request.get("/umami/script.js")).status()).toBe(200);
  for (const path of ["/umami", "/umami/", "/umami/login", "/umami/api/auth/login", "/umami/api/websites", "/umami/api/heartbeat", "/umami/api/send/x"]) {
    expect((await request.get(path)).status(), path).toBe(404);
    expect((await request.post(path, { data: {} })).status(), path).toBe(404);
  }
  expect((await request.get("/umami/api/send")).status()).toBe(404);
  expect((await request.post("/umami/script.js")).status()).toBe(404);
  const plain = await request.post("/umami/api/send", { headers: { "Content-Type": "text/plain" }, data: "{}" });
  expect(plain.status()).toBe(415);
  const big = await request.post("/umami/api/send", { headers: { "Content-Type": "application/json" }, data: JSON.stringify({ x: "y".repeat(9000) }) });
  expect(big.status()).toBe(413);
});

test("the address header written by a visitor is overwritten by the relay", async ({ request }) => {
  const agent = `mcplain-e2e-${randomUUID()}`;
  const answer = await request.post("/umami/api/send", {
    headers: { "Content-Type": "application/json", "User-Agent": agent, "x-mcplain-visitor-ip": "6.6.6.6", "X-Forwarded-For": "6.6.6.6", "X-Real-IP": "6.6.6.6" },
    data: JSON.stringify({ type: "event", payload: { website: TEST_WEBSITE_ID, url: "/fr", ip: "6.6.6.6" } }),
  });
  expect(answer.status()).toBe(200);
  const [record] = await records(request, agent);
  expect(record?.headers["x-mcplain-visitor-ip"]).toBe("127.0.0.1");
  expect(record?.headers["x-real-ip"]).toBeUndefined();
  expect(record?.headers["x-forwarded-for"]).toBeUndefined();
  expect(record?.body.payload.ip).toBeUndefined();
});
