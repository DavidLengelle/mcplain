export type AuthErrorKey =
  | "invalidCredentials"
  | "emailNotVerified"
  | "passwordLength"
  | "altcha"
  | "signupLimit"
  | "tooMany"
  | "invalidToken"
  | "wrongPassword"
  | "invalidEmail"
  | "unavailable";

export type AuthError = { code?: string | undefined; status?: number | undefined } | null | undefined;

const BY_CODE: Record<string, AuthErrorKey> = {
  INVALID_EMAIL_OR_PASSWORD: "invalidCredentials",
  USER_NOT_FOUND: "invalidCredentials",
  CREDENTIAL_ACCOUNT_NOT_FOUND: "invalidCredentials",
  EMAIL_NOT_VERIFIED: "emailNotVerified",
  PASSWORD_TOO_SHORT: "passwordLength",
  PASSWORD_TOO_LONG: "passwordLength",
  INVALID_PASSWORD: "wrongPassword",
  PASSWORD_REQUIRED: "wrongPassword",
  INVALID_EMAIL: "invalidEmail",
  ALTCHA_INVALID: "altcha",
  SIGNUP_LIMIT: "signupLimit",
  INVALID_TOKEN: "invalidToken",
  TOKEN_EXPIRED: "invalidToken",
};

export function authErrorKey(error: AuthError): AuthErrorKey {
  const code = error?.code ?? "";
  const known = BY_CODE[code];
  if (known !== undefined) {
    return known;
  }
  if (error?.status === 429) {
    return "tooMany";
  }
  return "unavailable";
}

export function verificationFailed(search: string): boolean {
  return new URLSearchParams(search).has("error");
}
