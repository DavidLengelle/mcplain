import { expect, test } from "@playwright/test";

import { ID, orangeView, serveAnalysis } from "./fake-api";

const EXPECTED: Record<string, string> = {
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=()",
  "cross-origin-opener-policy": "same-origin",
};

test("the production pages carry the security headers and a CSP with a nonce", async ({ request }) => {
  for (const path of ["/", "/fr", `/analyses/${ID}`]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(200);
    const headers = response.headers();
    for (const [name, value] of Object.entries(EXPECTED)) {
      expect(headers[name], `${path} ${name}`).toBe(value);
    }
    expect(headers["x-powered-by"]).toBeUndefined();
    const policy = headers["content-security-policy"];
    expect(policy).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("upgrade-insecure-requests");
    expect(policy).not.toContain("unsafe-eval");
    const nonce = /'nonce-([^']+)'/.exec(policy)?.[1];
    const html = await response.text();
    const scripts = html.match(/<script\b[^>]*>/g) ?? [];
    expect(scripts.length).toBeGreaterThan(0);
    for (const script of scripts) {
      expect(script, path).toContain(`nonce="${nonce}"`);
    }
  }
});

test("each request gets its own nonce", async ({ request }) => {
  const first = (await request.get("/")).headers()["content-security-policy"];
  const second = (await request.get("/")).headers()["content-security-policy"];
  expect(first).not.toBe(second);
});

test("static files also carry nosniff", async ({ request }) => {
  const response = await request.get("/icon.svg");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
});

test("the pages break no rule of the policy", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) {
      violations.push(message.text());
    }
  });
  await serveAnalysis(page, [orangeView()]);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.goto(`/fr/analyses/${ID}`);
  await expect(page.locator("[data-verdict-panel]")).toBeVisible();
  expect(violations).toEqual([]);
});
