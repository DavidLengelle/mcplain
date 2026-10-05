import { apiBaseUrl } from "./api-url";
import { engineCatalogToMessages, type MessageTree } from "./icu";

export const CACHE_MILLISECONDS = 60 * 60 * 1000;
export const RETRY_MILLISECONDS = 30 * 1000;
export const TIMEOUT_MILLISECONDS = 3000;

type Entry = { messages: MessageTree | null; expires: number };

const cache = new Map<string, Entry>();

export function clearEngineMessagesCache(): void {
  cache.clear();
}

async function download(locale: string): Promise<MessageTree | null> {
  try {
    const response = await fetch(`${apiBaseUrl()}/api/messages/${encodeURIComponent(locale)}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MILLISECONDS),
    });
    if (!response.ok) {
      return null;
    }
    return engineCatalogToMessages(await response.json());
  } catch {
    return null;
  }
}

export async function engineMessages(locale: string, now: number = Date.now()): Promise<MessageTree | null> {
  const entry = cache.get(locale);
  if (entry !== undefined && entry.expires > now) {
    return entry.messages;
  }
  const messages = await download(locale);
  if (messages !== null) {
    cache.set(locale, { messages, expires: now + CACHE_MILLISECONDS });
    return messages;
  }
  let previous: MessageTree | null = null;
  if (entry !== undefined) {
    previous = entry.messages;
  }
  cache.set(locale, { messages: previous, expires: now + RETRY_MILLISECONDS });
  return previous;
}
