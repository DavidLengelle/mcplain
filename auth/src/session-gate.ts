export const TWO_FACTOR_SESSION_PATHS: ReadonlySet<string> = new Set([
  "/sign-in/email",
  "/two-factor/verify-totp",
  "/two-factor/verify-backup-code",
  "/two-factor/enable",
  "/two-factor/disable",
  "/change-password",
]);

export const ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED";
export const TWO_FACTOR_REQUIRED = "TWO_FACTOR_REQUIRED";
export const SESSION_REFUSED = "SESSION_REFUSED";

export type SessionRefusal = typeof ACCOUNT_BLOCKED | typeof TWO_FACTOR_REQUIRED | typeof SESSION_REFUSED;

function field(record: object, name: string): unknown {
  return (record as Record<string, unknown>)[name];
}

export function sessionRefusal(user: unknown, path: string | undefined): SessionRefusal | null {
  if (typeof user !== "object" || user === null) {
    return SESSION_REFUSED;
  }
  const bannedAt = field(user, "bannedAt");
  if (bannedAt !== undefined && bannedAt !== null) {
    return ACCOUNT_BLOCKED;
  }
  const enabled = field(user, "twoFactorEnabled");
  if (enabled === false || enabled === undefined || enabled === null) {
    return null;
  }
  if (path === undefined || !TWO_FACTOR_SESSION_PATHS.has(path)) {
    return TWO_FACTOR_REQUIRED;
  }
  return null;
}
