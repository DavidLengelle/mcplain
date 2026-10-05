import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, createNonce, SECURITY_HEADERS } from "@/lib/security-headers";

function directives(policy: string): Map<string, string> {
  return new Map(
    policy.split("; ").map((directive) => {
      const [name, ...values] = directive.split(" ");
      return [name, values.join(" ")];
    }),
  );
}

describe("security headers", () => {
  it("give a fresh, unpredictable nonce for each request", () => {
    const nonces = new Set(Array.from({ length: 50 }, () => createNonce()));
    expect(nonces.size).toBe(50);
    for (const nonce of nonces) {
      expect(nonce).toMatch(/^[A-Za-z0-9+/=]{40,}$/);
    }
  });

  it("build a strict policy for production", () => {
    const policy = directives(contentSecurityPolicy("abc", false));
    expect(policy.get("default-src")).toBe("'self'");
    expect(policy.get("script-src")).toBe("'self' 'nonce-abc' 'strict-dynamic'");
    expect(policy.get("style-src")).toBe("'self' 'nonce-abc'");
    expect(policy.get("img-src")).toBe("'self' data:");
    expect(policy.get("font-src")).toBe("'self'");
    expect(policy.get("connect-src")).toBe("'self'");
    expect(policy.get("object-src")).toBe("'none'");
    expect(policy.get("base-uri")).toBe("'self'");
    expect(policy.get("form-action")).toBe("'self'");
    expect(policy.get("frame-ancestors")).toBe("'none'");
    expect(policy.has("upgrade-insecure-requests")).toBe(true);
    expect(contentSecurityPolicy("abc", false)).not.toContain("unsafe");
  });

  it("loosen only development: eval for React debugging, inline styles for the dev tools of Next.js", () => {
    const policy = directives(contentSecurityPolicy("abc", true));
    expect(policy.get("script-src")).toBe("'self' 'nonce-abc' 'strict-dynamic' 'unsafe-eval'");
    expect(policy.get("style-src")).toBe("'self' 'unsafe-inline'");
    expect(policy.has("upgrade-insecure-requests")).toBe(false);
  });

  it("turn off camera, microphone and location", () => {
    expect(SECURITY_HEADERS["Permissions-Policy"]).toBe("camera=(), microphone=(), geolocation=()");
  });
});
