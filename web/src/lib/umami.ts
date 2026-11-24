export const DEFAULT_UMAMI_URL = "http://127.0.0.1:3200";
export const UMAMI_HOST_PATH = "/umami";
export const UMAMI_SCRIPT_PATH = "/umami/script.js";
export const UMAMI_GUARD_PATH = "/umami-guard.js";
export const UMAMI_BEFORE_SEND = "mcplainUmamiBeforeSend";
export const VISITOR_IP_HEADER = "x-mcplain-visitor-ip";
export const SEND_BODY_MAX_BYTES = 8192;
export const ID_PLACEHOLDER = "[id]";

const ALLOWED_PROTOCOLS = ["http:", "https:"];
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ID_SEGMENT = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_-]{20,})$/i;
const LOCALE_SEGMENTS = new Set(["en", "fr"]);
const HIDDEN_SECTIONS = new Set(["admin", "account"]);
const MAX_HOPS = 5;
const MAX_ENTRIES = 32;
const IPV4 = /^(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;
const IPV4_MAPPED = /^::ffff:((?:\d{1,3}\.){3}\d{1,3})$/i;
const TEXT_LIMITS = { hostname: 253, language: 35, screen: 11, title: 500, url: 1000, referrer: 1000 } as const;
const USER_AGENT_MAX = 512;
const CACHE_TOKEN_MAX = 2048;

type Json = Record<string, unknown>;

export function umamiBaseUrl(value: string | undefined = process.env.MCPLAIN_UMAMI_URL): string {
  const text = (value ?? "").trim();
  if (text === "") {
    return DEFAULT_UMAMI_URL;
  }
  const url = new URL(text);
  if (!ALLOWED_PROTOCOLS.includes(url.protocol)) {
    throw new Error("MCPLAIN_UMAMI_URL must start with http:// or https://");
  }
  return url.origin;
}

export function websiteId(value: string | undefined = process.env.MCPLAIN_UMAMI_WEBSITE_ID): string | null {
  const text = (value ?? "").trim().toLowerCase();
  if (UUID_PATTERN.test(text)) {
    return text;
  }
  return null;
}

export function proxyHops(value: string | undefined = process.env.MCPLAIN_TRUSTED_PROXY_HOPS): number {
  const parsed = Number.parseInt((value ?? "").trim(), 10);
  if (Number.isInteger(parsed) && parsed >= 0 && parsed <= MAX_HOPS) {
    return parsed;
  }
  return 1;
}

function groupsOf(text: string | undefined): string[] {
  if (text === undefined || text === "") {
    return [];
  }
  return text.split(":");
}

function expandIpv6(text: string): number[] | null {
  const halves = text.split("::");
  if (halves.length > 2) {
    return null;
  }
  const head = groupsOf(halves[0]);
  const tail = groupsOf(halves[1]);
  const missing = 8 - head.length - tail.length;
  if (halves.length === 2 && missing < 1) {
    return null;
  }
  if (halves.length === 1 && missing !== 0) {
    return null;
  }
  const groups = [...head, ...Array<string>(Math.max(0, missing)).fill("0"), ...tail];
  const numbers: number[] = [];
  for (const group of groups) {
    if (!/^[0-9a-f]{1,4}$/i.test(group)) {
      return null;
    }
    numbers.push(Number.parseInt(group, 16));
  }
  return numbers;
}

export function normalizeAddress(text: string | null | undefined): string | null {
  if (text === null || text === undefined) {
    return null;
  }
  const candidate = text.trim().replace(/^\[|\]$/g, "").split("%")[0] ?? "";
  const mapped = IPV4_MAPPED.exec(candidate);
  if (mapped !== null && IPV4.test(mapped[1] ?? "")) {
    return mapped[1] ?? null;
  }
  if (IPV4.test(candidate)) {
    return candidate;
  }
  const groups = expandIpv6(candidate);
  if (groups === null) {
    return null;
  }
  const network = groups.slice(0, 4).map((group) => group.toString(16));
  return `${network.join(":")}::`;
}

export function visitorAddress(forwardedFor: string | null, hops: number): string | null {
  if (hops === 0 || forwardedFor === null) {
    return null;
  }
  const entries = forwardedFor
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
  if (entries.length < hops || entries.length > MAX_ENTRIES) {
    return null;
  }
  return normalizeAddress(entries[entries.length - hops]);
}

function withoutLocale(segments: string[]): string[] {
  if (segments.length > 0 && LOCALE_SEGMENTS.has(segments[0] ?? "")) {
    return segments.slice(1);
  }
  return segments;
}

export function cleanPath(pathname: string): string {
  const segments = pathname.split("/").map((segment) => {
    if (ID_SEGMENT.test(segment)) {
      return ID_PLACEHOLDER;
    }
    return segment;
  });
  return segments.join("/") || "/";
}

export function isHiddenPath(pathname: string): boolean {
  const segments = withoutLocale(pathname.split("/").filter((segment) => segment !== ""));
  return segments.length > 0 && HIDDEN_SECTIONS.has(segments[0] ?? "");
}

function text(value: unknown, limit: number): string | null {
  if (typeof value === "string" && value.length <= limit) {
    return value;
  }
  return null;
}

function pathOf(value: string, base: URL): URL | null {
  try {
    return new URL(value, base);
  } catch {
    return null;
  }
}

export function cleanSend(value: unknown, site: string, origin: string): Json | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const body = value as Json;
  if (body.type !== "event") {
    return null;
  }
  const payload = body.payload;
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  const sent = payload as Json;
  if (sent.website !== site || "name" in sent || "data" in sent) {
    return null;
  }
  const base = new URL(origin);
  const rawUrl = text(sent.url, TEXT_LIMITS.url);
  if (rawUrl === null) {
    return null;
  }
  const page = pathOf(rawUrl, base);
  if (page === null || page.host !== base.host || isHiddenPath(page.pathname)) {
    return null;
  }
  const clean: Json = { website: site, url: cleanPath(page.pathname) };
  for (const key of ["hostname", "language", "screen", "title"] as const) {
    const kept = text(sent[key], TEXT_LIMITS[key]);
    if (kept !== null) {
      clean[key] = kept;
    }
  }
  const rawReferrer = text(sent.referrer, TEXT_LIMITS.referrer);
  if (rawReferrer !== null && rawReferrer !== "") {
    const referrer = pathOf(rawReferrer, base);
    if (referrer !== null && referrer.host === base.host) {
      clean.referrer = cleanPath(referrer.pathname);
    } else if (referrer !== null && ALLOWED_PROTOCOLS.includes(referrer.protocol)) {
      clean.referrer = referrer.origin;
    }
  }
  return { type: "event", payload: clean };
}

export function forwardedHeaders(incoming: Headers, address: string | null): Headers {
  const headers = new Headers({ "Content-Type": "application/json", Accept: "application/json" });
  const agent = incoming.get("user-agent");
  if (agent !== null && agent.length <= USER_AGENT_MAX) {
    headers.set("User-Agent", agent);
  }
  const cache = incoming.get("x-umami-cache");
  if (cache !== null && cache.length <= CACHE_TOKEN_MAX && /^[A-Za-z0-9._-]+$/.test(cache)) {
    headers.set("x-umami-cache", cache);
  }
  if (address !== null) {
    headers.set(VISITOR_IP_HEADER, address);
  }
  return headers;
}

export async function readLimited(request: Request, limit: number): Promise<string | null> {
  const declared = request.headers.get("content-length");
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > limit)) {
    return null;
  }
  if (request.body === null) {
    return "";
  }
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}
