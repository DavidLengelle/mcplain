import { describe, expect, it } from "vitest";

import { apiBaseUrl, DEFAULT_API_URL, DEFAULT_GUICHET_URL, guichetBaseUrl, relayRewrites } from "@/lib/api-url";

describe("apiBaseUrl", () => {
  it("defaults to the local API", () => {
    expect(apiBaseUrl(undefined)).toBe(DEFAULT_API_URL);
    expect(apiBaseUrl("  ")).toBe("http://127.0.0.1:8000");
  });

  it("keeps only the origin", () => {
    expect(apiBaseUrl("http://api:8000/")).toBe("http://api:8000");
    expect(apiBaseUrl(" https://api.example.com/x/ ")).toBe("https://api.example.com");
  });

  it("refuses other protocols and broken addresses", () => {
    expect(() => apiBaseUrl("file:///etc/passwd")).toThrow();
    expect(() => apiBaseUrl("not a url")).toThrow();
  });
});

describe("relayRewrites", () => {
  it("sends /api/auth/* to the counter before /api/* goes to the API, and nothing else", () => {
    const rewrites = relayRewrites("http://api:8000", "http://guichet:3100");
    expect(rewrites).toEqual([
      { source: "/api/auth/:path*", destination: "http://guichet:3100/api/auth/:path*" },
      { source: "/api/:path*", destination: "http://api:8000/api/:path*" },
    ]);
    for (const rewrite of rewrites) {
      expect(rewrite.source.startsWith("/api/")).toBe(true);
      expect(rewrite.destination).not.toContain("/internal");
    }
  });

  it("defaults to the local counter", () => {
    expect(guichetBaseUrl(undefined)).toBe(DEFAULT_GUICHET_URL);
    expect(guichetBaseUrl("http://guichet:3100/")).toBe("http://guichet:3100");
    expect(() => guichetBaseUrl("file:///etc/passwd")).toThrow();
  });
});
