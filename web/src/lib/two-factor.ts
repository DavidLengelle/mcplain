export const CODE_DIGITS = 6;
export const KEY_GROUP = 4;
export const ROLE_ADMIN = "admin";

const BASE32 = /^[A-Z2-7]+=*$/;

export function secretFromUri(uri: string): string | null {
  let url: URL;
  try {
    url = new URL(uri);
  } catch {
    return null;
  }
  if (url.protocol !== "otpauth:") {
    return null;
  }
  const secret = (url.searchParams.get("secret") ?? "").toUpperCase().replace(/=+$/, "");
  if (secret === "" || !BASE32.test(secret)) {
    return null;
  }
  return secret;
}

export function keyGroups(secret: string): string[] {
  const groups: string[] = [];
  for (let index = 0; index < secret.length; index += KEY_GROUP) {
    groups.push(secret.slice(index, index + KEY_GROUP));
  }
  return groups;
}

export function typedCode(text: string): string {
  return text.replace(/\D/g, "").slice(0, CODE_DIGITS);
}

export function typedBackupCode(text: string): string {
  return text.replace(/\s/g, "").slice(0, 64);
}

function field(user: unknown, name: string): unknown {
  if (typeof user !== "object" || user === null) {
    return undefined;
  }
  return (user as Record<string, unknown>)[name];
}

export function isAdminRole(user: unknown): boolean {
  return field(user, "role") === ROLE_ADMIN;
}

export function hasTwoFactor(user: unknown): boolean {
  return field(user, "twoFactorEnabled") === true;
}

export function asksSecondFactor(data: unknown): boolean {
  return field(data, "twoFactorRedirect") === true;
}
