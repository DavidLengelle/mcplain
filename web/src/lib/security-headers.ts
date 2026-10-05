export const SECURITY_HEADERS: Record<string, string> = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

export function createNonce(): string {
  return btoa(crypto.randomUUID());
}

export function contentSecurityPolicy(nonce: string, development: boolean): string {
  const scripts = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  let styles = `'self' 'nonce-${nonce}'`;
  if (development) {
    scripts.push("'unsafe-eval'");
    styles = "'self' 'unsafe-inline'";
  }
  const directives = [
    "default-src 'self'",
    `script-src ${scripts.join(" ")}`,
    `style-src ${styles}`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!development) {
    directives.push("upgrade-insecure-requests");
  }
  return directives.join("; ");
}
