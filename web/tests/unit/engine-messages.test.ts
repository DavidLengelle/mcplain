import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CACHE_MILLISECONDS,
  clearEngineMessagesCache,
  engineMessages,
  RETRY_MILLISECONDS,
} from "@/lib/engine-messages";

const CATALOG = { "status.ok": "analysis done", "cli.places": "{count} place(s)" };

function answer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("engine messages", () => {
  beforeEach(() => {
    clearEngineMessagesCache();
    vi.stubEnv("MCPLAIN_API_URL", "http://api.test:8000/");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("asks GET /api/messages/{lang} and nests the catalog", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(CATALOG));
    const messages = await engineMessages("fr", 0);
    expect(messages).toEqual({ status: { ok: "analysis done" }, cli: { places: "{count} place(s)" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test:8000/api/messages/fr");
  });

  it("keeps the texts one hour, then asks again", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => answer(CATALOG));
    await engineMessages("en", 0);
    await engineMessages("en", CACHE_MILLISECONDS - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await engineMessages("en", CACHE_MILLISECONDS + 1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives null when the API cannot be reached, and waits before trying again", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    expect(await engineMessages("en", 0)).toBeNull();
    expect(await engineMessages("en", RETRY_MILLISECONDS - 1)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await engineMessages("en", RETRY_MILLISECONDS + 1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["an error status", () => answer({ error: { code: "api.unknown_language" } }, 404)],
    ["a list", () => answer(["status.ok"])],
    ["text that is not JSON", () => new Response("<html>", { status: 200 })],
  ])("gives null for %s", async (_name, response) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => response());
    expect(await engineMessages("en", 0)).toBeNull();
  });

  it("keeps the last good texts when a later refresh fails", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => answer(CATALOG));
    const good = await engineMessages("en", 0);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect(await engineMessages("en", CACHE_MILLISECONDS + 1)).toEqual(good);
  });
});
