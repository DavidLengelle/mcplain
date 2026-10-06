import type { NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";
import { contentSecurityPolicy, createNonce, NONCE_HEADER, SECURITY_HEADERS } from "./lib/security-headers";

const CSP_HEADER = "Content-Security-Policy";

const handleI18nRouting = createMiddleware(routing);

export default function proxy(request: NextRequest) {
  const nonce = createNonce();
  const policy = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  request.headers.set(CSP_HEADER, policy);
  request.headers.set(NONCE_HEADER, nonce);
  const response = handleI18nRouting(request);
  response.headers.set(CSP_HEADER, policy);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
