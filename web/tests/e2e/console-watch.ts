import type { Page } from "@playwright/test";

const SETTLE_MS = 2000;

export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("load");
  await page.waitForTimeout(SETTLE_MS);
}

export function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      problems.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => problems.push(`page: ${String(error)}`));
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    const aborted = failure === "net::ERR_ABORTED" && request.url().includes("_rsc=");
    if (!aborted) {
      problems.push(`request: ${request.url()} ${failure}`);
    }
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/en") {
      if (request.isNavigationRequest()) {
        return;
      }
      problems.push(`background request: ${request.url()}`);
    }
  });
  return problems;
}
