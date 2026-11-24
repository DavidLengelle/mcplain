import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as catchAll from "@/app/umami/[[...path]]/route";
import * as send from "@/app/umami/api/send/route";
import * as script from "@/app/umami/script.js/route";
import { cleanPath, cleanSend, forwardedHeaders, isHiddenPath, normalizeAddress, visitorAddress, VISITOR_IP_HEADER } from "@/lib/umami";

const SITE = "b59e9c65-ae32-47f1-8400-119fcf4861c4";
const REPORT = "5b0c6f2e-8d3a-4c1b-9e7f-0a1b2c3d4e5f";
const ORIGIN = "http://localhost:3000";
const FIXTURE = join(process.cwd(), "tests", "fixtures", "umami-script-3.4.1.js");
const FIXTURE_SHA256 = "654f12c7548be726eba5b71d5ef8bffc2a41a39a0053e2a49a847869ccd7ac3f";

type Sent = { url: string; init: RequestInit };

function pageview(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "event",
    payload: {
      website: SITE,
      hostname: "localhost",
      language: "fr-FR",
      screen: "1280x800",
      title: "Rapport d'analyse, MCPlain",
      url: `/fr/analyses/${REPORT}`,
      referrer: "",
      ...overrides,
    },
  };
}

function stubUmami(status = 200, body = '{"cache":"x"}'): Sent[] {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      sent.push({ url, init });
      return new Response(body, { status, headers: { "Content-Type": "application/json", "Set-Cookie": "umami=1" } });
    }),
  );
  return sent;
}

function post(body: string, headers: Record<string, string> = {}): Request {
  return new Request(`${ORIGIN}/umami/api/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
  });
}

beforeEach(() => {
  vi.stubEnv("MCPLAIN_UMAMI_URL", "http://umami:3000");
  vi.stubEnv("MCPLAIN_UMAMI_WEBSITE_ID", SITE);
  vi.stubEnv("MCPLAIN_TRUSTED_PROXY_HOPS", "1");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("the paths sent to Umami", () => {
  it("replace every identifier by [id], keep the rest, and hide the admin and account pages", () => {
    expect(cleanPath(`/fr/analyses/${REPORT}`)).toBe("/fr/analyses/[id]");
    expect(cleanPath(`/analyses/${REPORT.toUpperCase()}`)).toBe("/analyses/[id]");
    expect(cleanPath("/fr/account/new-password/abcdefghijklmnopqrstuvwxyz012345")).toBe("/fr/account/new-password/[id]");
    expect(cleanPath("/")).toBe("/");
    expect(cleanPath("/fr")).toBe("/fr");
    expect(isHiddenPath("/admin")).toBe(true);
    expect(isHiddenPath("/fr/admin")).toBe(true);
    expect(isHiddenPath("/account/sign-in")).toBe(true);
    expect(isHiddenPath("/fr/account")).toBe(true);
    expect(isHiddenPath("/fr/analyses/x")).toBe(false);
    expect(isHiddenPath("/administration")).toBe(false);
  });
});

describe("the address given to Umami", () => {
  it("is the one our relay appended, counted from the right; what the browser wrote is never trusted", () => {
    expect(visitorAddress("203.0.113.5", 1)).toBe("203.0.113.5");
    expect(visitorAddress("6.6.6.6, 203.0.113.5", 1)).toBe("203.0.113.5");
    expect(visitorAddress("6.6.6.6, 203.0.113.5, 10.0.0.2", 2)).toBe("203.0.113.5");
    expect(visitorAddress("203.0.113.5", 2)).toBeNull();
    expect(visitorAddress("203.0.113.5", 0)).toBeNull();
    expect(visitorAddress(null, 1)).toBeNull();
    expect(visitorAddress("not-an-address", 1)).toBeNull();
  });

  it("keeps an IPv4 address, and only the /64 network of an IPv6 address", () => {
    expect(normalizeAddress("::ffff:203.0.113.5")).toBe("203.0.113.5");
    expect(normalizeAddress("2001:db8:1:2:3:4:5:6")).toBe("2001:db8:1:2::");
    expect(normalizeAddress("[2001:db8::1]")).toBe("2001:db8:0:0::");
    expect(normalizeAddress("fe80::1%eth0")).toBe("fe80:0:0:0::");
    expect(normalizeAddress("1.2.3")).toBeNull();
    expect(normalizeAddress("2001:db8::1::2")).toBeNull();
  });
});

describe("the body sent to Umami", () => {
  it("keeps a page view only, with the known fields, the path cleaned and nothing else", () => {
    const body = pageview({ url: `http://localhost:3000/fr/analyses/${REPORT}?token=secret#tool-x`, ip: "6.6.6.6", userAgent: "fake", id: "someone", tag: "t", timestamp: 1 });
    expect(cleanSend(body, SITE, ORIGIN)).toEqual({
      type: "event",
      payload: { website: SITE, url: "/fr/analyses/[id]", hostname: "localhost", language: "fr-FR", screen: "1280x800", title: "Rapport d'analyse, MCPlain" },
    });
  });

  it("cuts an outside referrer to its origin and cleans a referrer of the site", () => {
    const outside = cleanSend(pageview({ referrer: "https://news.example.com/item?id=42" }), SITE, ORIGIN);
    expect((outside?.payload as Record<string, unknown>).referrer).toBe("https://news.example.com");
    const inside = cleanSend(pageview({ referrer: `/analyses/${REPORT}` }), SITE, ORIGIN);
    expect((inside?.payload as Record<string, unknown>).referrer).toBe("/analyses/[id]");
    const strange = cleanSend(pageview({ referrer: "javascript:alert(1)" }), SITE, ORIGIN);
    expect(strange?.payload).not.toHaveProperty("referrer");
  });

  it("refuses the admin and account pages, another website, another host, an identify, an event and odd shapes", () => {
    for (const url of ["/admin", "/fr/admin", "/account", "/fr/account/sign-in", "https://other.example.com/fr"]) {
      expect(cleanSend(pageview({ url }), SITE, ORIGIN)).toBeNull();
    }
    expect(cleanSend(pageview({ website: "00000000-0000-4000-8000-000000000000" }), SITE, ORIGIN)).toBeNull();
    expect(cleanSend({ ...pageview(), type: "identify" }, SITE, ORIGIN)).toBeNull();
    expect(cleanSend(pageview({ name: "click" }), SITE, ORIGIN)).toBeNull();
    expect(cleanSend(pageview({ data: { a: 1 } }), SITE, ORIGIN)).toBeNull();
    expect(cleanSend(pageview({ url: 42 }), SITE, ORIGIN)).toBeNull();
    expect(cleanSend([], SITE, ORIGIN)).toBeNull();
    expect(cleanSend(null, SITE, ORIGIN)).toBeNull();
  });
});

describe("the headers sent to Umami", () => {
  it("are built from scratch: our address header overwrites the one of the visitor, and no other address header passes", () => {
    const incoming = new Headers({
      "user-agent": "Mozilla/5.0",
      cookie: "mcplain.session_token=secret",
      [VISITOR_IP_HEADER]: "6.6.6.6",
      "x-forwarded-for": "6.6.6.6",
      "x-real-ip": "6.6.6.6",
      "cf-connecting-ip": "6.6.6.6",
      "true-client-ip": "6.6.6.6",
      forwarded: "for=6.6.6.6",
      "cf-ipcountry": "XX",
      "x-umami-cache": "a.b-c_d",
    });
    const headers = forwardedHeaders(incoming, "203.0.113.5");
    expect(Object.fromEntries(headers.entries())).toEqual({
      accept: "application/json",
      "content-type": "application/json",
      "user-agent": "Mozilla/5.0",
      "x-umami-cache": "a.b-c_d",
      [VISITOR_IP_HEADER]: "203.0.113.5",
    });
    expect(forwardedHeaders(new Headers({ [VISITOR_IP_HEADER]: "6.6.6.6" }), null).has(VISITOR_IP_HEADER)).toBe(false);
  });
});

describe("the relay of the website", () => {
  it("passes a page view to Umami with the cleaned body, our headers and the address of the visitor", async () => {
    const sent = stubUmami();
    const answer = await send.POST(
      post(JSON.stringify(pageview({ ip: "6.6.6.6" })), { "x-forwarded-for": "6.6.6.6, 203.0.113.5", [VISITOR_IP_HEADER]: "6.6.6.6", "x-real-ip": "6.6.6.6" }),
    );
    expect(answer.status).toBe(200);
    expect(answer.headers.get("set-cookie")).toBeNull();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.url).toBe("http://umami:3000/api/send");
    const headers = new Headers(sent[0]?.init.headers);
    expect(headers.get(VISITOR_IP_HEADER)).toBe("203.0.113.5");
    expect(headers.has("x-real-ip")).toBe(false);
    expect(headers.has("x-forwarded-for")).toBe(false);
    expect(JSON.parse(String(sent[0]?.init.body))).toEqual(cleanSend(pageview(), SITE, ORIGIN));
    expect(sent[0]?.init.redirect).toBe("error");
  });

  it("refuses another type than JSON (415) and a body over 8 KB (413), without calling Umami", async () => {
    const sent = stubUmami();
    const plain = new Request(`${ORIGIN}/umami/api/send`, { method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify(pageview()) });
    expect((await send.POST(plain)).status).toBe(415);
    const big = JSON.stringify(pageview({ title: "x".repeat(9000) }));
    expect((await send.POST(post(big))).status).toBe(413);
    const lying = new Request(`${ORIGIN}/umami/api/send`, { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": "100" }, body: big });
    expect((await send.POST(lying)).status).toBe(413);
    expect((await send.POST(post("{not json"))).status).toBe(400);
    expect((await send.POST(post(JSON.stringify(pageview({ url: "/fr/admin" }))))).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it("answers 404 when no website is set, and for every other method or path under /umami", async () => {
    const sent = stubUmami();
    vi.stubEnv("MCPLAIN_UMAMI_WEBSITE_ID", "");
    expect((await send.POST(post(JSON.stringify(pageview())))).status).toBe(404);
    expect((await script.GET()).status).toBe(404);
    for (const handler of [send.GET, send.PUT, send.DELETE, script.POST, catchAll.GET, catchAll.POST, catchAll.PUT, catchAll.DELETE, catchAll.PATCH, catchAll.OPTIONS]) {
      expect(handler().status).toBe(404);
    }
    expect(sent).toHaveLength(0);
  });

  it("serves the tracker script of Umami as JavaScript", async () => {
    const sent = stubUmami(200, "(function(){})();");
    const answer = await script.GET();
    expect(answer.status).toBe(200);
    expect(answer.headers.get("content-type")).toBe("application/javascript; charset=utf-8");
    expect(await answer.text()).toBe("(function(){})();");
    expect(sent[0]?.url).toBe("http://umami:3000/script.js");
  });
});

describe("the guard of the browser", () => {
  it("does what the relay does, before anything leaves the browser", async () => {
    const location = pathToFileURL(join(process.cwd(), "public", "umami-guard.js")).href;
    await import(location);
    const guard = (window as unknown as { mcplainUmamiBeforeSend: (type: string, payload: unknown) => unknown }).mcplainUmamiBeforeSend;
    const page = (url: string, referrer = "") => ({ website: SITE, hostname: "localhost", title: "t", url, referrer, id: "x", tag: "y" });
    expect(guard("event", page(`${window.location.origin}/fr/analyses/${REPORT}?q=1#a`, "https://news.example.com/x?y=1"))).toEqual({
      url: "/fr/analyses/[id]",
      website: SITE,
      hostname: "localhost",
      title: "t",
      referrer: "https://news.example.com",
    });
    expect(guard("event", page(`/analyses/${REPORT}`, `/fr/analyses/${REPORT}`))).toMatchObject({ url: "/analyses/[id]", referrer: "/fr/analyses/[id]" });
    for (const url of ["/admin", "/fr/admin", "/account/sign-in", "/fr/account", "https://other.example.com/"]) {
      expect(guard("event", page(url))).toBeNull();
    }
    expect(guard("identify", page("/"))).toBeNull();
    expect(guard("event", { ...page("/"), name: "click" })).toBeNull();
    Object.defineProperty(window.navigator, "globalPrivacyControl", { value: true, configurable: true });
    expect(guard("event", page("/"))).toBeNull();
    Object.defineProperty(window.navigator, "globalPrivacyControl", { value: undefined, configurable: true });
  });
});

describe("the copy of the tracker script of Umami 3.4.1", () => {
  it("is the one of the pinned image, and it never writes a cookie nor the browser storage", () => {
    const content = readFileSync(FIXTURE);
    expect(createHash("sha256").update(content).digest("hex")).toBe(FIXTURE_SHA256);
    const text = content.toString("utf-8");
    expect(text).not.toContain("document.cookie");
    expect(text).not.toContain("setItem");
    expect(text).toContain("before-send");
    expect(text).toContain("do-not-track");
  });
});
