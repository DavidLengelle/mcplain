export const ADMIN_ACCOUNTS_PATH = "/api/admin/accounts";
export const BAN_REASON_MAX_CHARACTERS = 200;

export type AdminAccount = {
  id: string;
  email: string;
  role: string;
  emailVerified: boolean;
  twoFactor: boolean;
  createdAt: string | null;
  bannedAt: string | null;
  banReason: string | null;
};

export type FindOutcome = { kind: "found"; account: AdminAccount } | { kind: "missing" } | { kind: "refused" } | { kind: "failed" };

export type ChangeOutcome = "done" | "self" | "admin" | "missing" | "refused" | "failed";

const CHANGE_BY_CODE: Record<string, ChangeOutcome> = {
  "api.cannot_ban_self": "self",
  "api.cannot_ban_admin": "admin",
  "api.account_not_found": "missing",
  "api.admin_required": "refused",
  "api.origin_refused": "refused",
};

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return null;
}

export function parseAccount(value: unknown): AdminAccount | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const account = (value as Record<string, unknown>).account;
  if (typeof account !== "object" || account === null) {
    return null;
  }
  const item = account as Record<string, unknown>;
  const id = text(item.id);
  const email = text(item.email);
  if (id === null || email === null) {
    return null;
  }
  return {
    id,
    email,
    role: text(item.role) ?? "user",
    emailVerified: item.email_verified === true,
    twoFactor: item.two_factor === true,
    createdAt: text(item.created_at),
    bannedAt: text(item.banned_at),
    banReason: text(item.ban_reason),
  };
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null) {
      const error = (body as Record<string, unknown>).error;
      if (typeof error === "object" && error !== null) {
        return text((error as Record<string, unknown>).code) ?? "";
      }
    }
  } catch {
    return "";
  }
  return "";
}

export async function findAccount(email: string): Promise<FindOutcome> {
  try {
    const query = new URLSearchParams({ email: email.trim() });
    const response = await fetch(`${ADMIN_ACCOUNTS_PATH}?${query.toString()}`, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (response.status === 404) {
      return { kind: "missing" };
    }
    if (response.status === 403) {
      return { kind: "refused" };
    }
    if (!response.ok) {
      return { kind: "failed" };
    }
    const account = parseAccount(await response.json());
    if (account === null) {
      return { kind: "failed" };
    }
    return { kind: "found", account };
  } catch {
    return { kind: "failed" };
  }
}

async function change(path: string, body: unknown): Promise<ChangeOutcome> {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (response.ok) {
      return "done";
    }
    return CHANGE_BY_CODE[await errorCode(response)] ?? "failed";
  } catch {
    return "failed";
  }
}

export function banAccount(id: string, reason: string): Promise<ChangeOutcome> {
  let sent: string | null = reason.trim();
  if (sent === "") {
    sent = null;
  }
  return change(`${ADMIN_ACCOUNTS_PATH}/${encodeURIComponent(id)}/ban`, { reason: sent });
}

export function unbanAccount(id: string): Promise<ChangeOutcome> {
  return change(`${ADMIN_ACCOUNTS_PATH}/${encodeURIComponent(id)}/unban`, {});
}
