import { createAuthClient } from "better-auth/react";

export const AUTH_BASE_PATH = "/api/auth";
export const LANG_HEADER = "x-mcplain-lang";
export const ALTCHA_HEADER = "x-altcha";
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;

export const authClient = createAuthClient({ basePath: AUTH_BASE_PATH });

export function authHeaders(locale: string, altcha: string | null = null): Record<string, string> {
  const headers: Record<string, string> = { [LANG_HEADER]: locale };
  if (altcha !== null) {
    headers[ALTCHA_HEADER] = altcha;
  }
  return headers;
}

export function passwordFits(password: string): boolean {
  return password.length >= MIN_PASSWORD_LENGTH && password.length <= MAX_PASSWORD_LENGTH;
}
