import { describe, expect, it } from "vitest";

import { apiBaseUrl, DEFAULT_API_URL } from "@/lib/api-url";

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
