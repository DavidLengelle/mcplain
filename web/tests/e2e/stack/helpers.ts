import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, type APIRequestContext, type Page } from "@playwright/test";

const MAILPIT = process.env.MCPLAIN_MAILPIT_URL ?? "http://127.0.0.1:8025";
const REPOSITORY = join(__dirname, "..", "..", "..", "..");
export const SCREENS = join(__dirname, "..", "..", "..", "test-results", "screens");
export const RESULTS = join(__dirname, "..", "..", "..", "test-results");
const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;
const LINK = /https?:\/\/\S+/;

export function site(baseURL: string | undefined, path: string): string {
  const url = new URL(path, baseURL);
  url.hostname = "localhost";
  return url.toString();
}

type MailSummary = { ID: string; Subject: string; To: { Address: string }[] };

export async function waitForMail(request: APIRequestContext, address: string, subject: RegExp): Promise<{ text: string; html: string }> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const listing = await request.get(`${MAILPIT}/api/v1/messages`, { params: { limit: "200" } });
    const body = (await listing.json()) as { messages: MailSummary[] };
    const found = body.messages.find(
      (message) => subject.test(message.Subject) && message.To.some((recipient) => recipient.Address === address),
    );
    if (found !== undefined) {
      const message = (await (await request.get(`${MAILPIT}/api/v1/message/${found.ID}`)).json()) as { Text: string; HTML: string };
      await request.delete(`${MAILPIT}/api/v1/messages`, { data: { IDs: [found.ID] } });
      return { text: message.Text, html: message.HTML };
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`no mail for ${address}`);
}

function quoted(addresses: string[]): string {
  return addresses.map((address) => `'${address.replaceAll("'", "''")}'`).join(", ");
}

async function mailsOf(request: APIRequestContext, address: string): Promise<string[]> {
  const found = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${address}"`, limit: "200" } });
  expect(found.ok()).toBe(true);
  const body = (await found.json()) as { messages: MailSummary[] };
  return body.messages.map((message) => message.ID);
}

export async function cleanUp(request: APIRequestContext, addresses: string[]): Promise<void> {
  if (addresses.length === 0) {
    return;
  }
  psql(`DELETE FROM auth."user" WHERE email IN (${quoted(addresses)});`);
  const deadline = Date.now() + 60_000;
  while (psql(`SELECT count(*) FROM mail_outbox WHERE recipient IN (${quoted(addresses)});`).trim() !== "0") {
    if (Date.now() > deadline) {
      throw new Error("the postman did not send the mails of the test");
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  for (const address of addresses) {
    const identifiers = await mailsOf(request, address);
    if (identifiers.length > 0) {
      const deleted = await request.delete(`${MAILPIT}/api/v1/messages`, { data: { IDs: identifiers } });
      expect(deleted.ok()).toBe(true);
    }
    expect(await mailsOf(request, address)).toEqual([]);
  }
}

export function linkOf(text: string): string {
  const match = LINK.exec(text);
  if (match === null) {
    throw new Error("the mail has no link");
  }
  return match[0];
}

export async function signIn(page: Page, baseURL: string | undefined, email: string, password: string) {
  await page.goto(site(baseURL, "/fr/account/sign-in"));
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe", { exact: true }).fill(password);
  await page.getByRole("button", { name: "SE CONNECTER" }).click();
}

export async function screens(page: Page, baseURL: string | undefined, path: string, name: string, ready: string) {
  mkdirSync(SCREENS, { recursive: true });
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(site(baseURL, path));
      await expect(page.locator(ready).first()).toBeVisible();
      await page.screenshot({ path: join(SCREENS, `${name}-${theme}-${width}.png`), fullPage: true });
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "light" });
}

export function psql(statement: string): string {
  return execFileSync("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "mcplain", "-d", "mcplain", "-At", "-c", statement], {
    cwd: REPOSITORY,
    encoding: "utf-8",
  });
}

export function resetCounters(): void {
  psql("DELETE FROM quota_usage; DELETE FROM burst_counts; DELETE FROM analysis_tokens;");
}
