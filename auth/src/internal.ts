import type { createAuth } from "./auth.ts";

export type Auth = ReturnType<typeof createAuth>;

export type InternalRequest = { method: string; path: string; search: URLSearchParams; cookie: string | undefined; body: string };

export type InternalAnswer = { status: number; body: unknown };

export const INTERNAL_PREFIX = "/internal/";
export const SESSION_ROUTE = "/internal/session";
export const ACCOUNTS_ROUTE = "/internal/accounts";
export const BAN_ROUTE = "/internal/accounts/ban";
export const UNBAN_ROUTE = "/internal/accounts/unban";
export const INTERNAL_BODY_MAX_BYTES = 2048;
export const BAN_REASON_MAX_CHARS = 200;
const COOKIE_MAX_CHARS = 8192;
const EMAIL_MAX_CHARS = 320;
const USER_ID_MAX_CHARS = 64;
const ROLE_ADMIN = "admin";

const NOT_FOUND: InternalAnswer = { status: 404, body: { error: "not_found" } };
const INVALID: InternalAnswer = { status: 400, body: { error: "invalid_request" } };
const IS_ADMIN: InternalAnswer = { status: 409, body: { error: "is_admin" } };
const DONE: InternalAnswer = { status: 200, body: { ok: true } };

export type SessionUser = { id: string; emailVerified: boolean; role: string; twoFactorEnabled: boolean; banned: boolean };

function field(record: unknown, name: string): unknown {
  if (typeof record !== "object" || record === null || !(name in record)) {
    return undefined;
  }
  return (record as Record<string, unknown>)[name];
}

export function sessionUser(user: unknown): SessionUser | null {
  const id = field(user, "id");
  if (typeof id !== "string" || id === "") {
    return null;
  }
  let role = "user";
  const stored = field(user, "role");
  if (typeof stored === "string") {
    role = stored;
  }
  return {
    id,
    emailVerified: field(user, "emailVerified") === true,
    role,
    twoFactorEnabled: field(user, "twoFactorEnabled") === true,
    banned: isBanned(user),
  };
}

export function isBanned(user: unknown): boolean {
  const value = field(user, "bannedAt");
  return value !== undefined && value !== null;
}

async function currentSession(auth: Auth, cookie: string | undefined): Promise<InternalAnswer> {
  if (cookie === undefined || cookie === "" || cookie.length > COOKIE_MAX_CHARS) {
    return { status: 200, body: { user: null } };
  }
  const data = await auth.api.getSession({ headers: new Headers({ cookie }) });
  if (data === null) {
    return { status: 200, body: { user: null } };
  }
  const context = await auth.$context;
  const stored = await context.internalAdapter.findUserById(data.user.id);
  const user = sessionUser(stored);
  if (user === null) {
    return { status: 200, body: { user: null } };
  }
  return { status: 200, body: { user } };
}

function isoDate(value: unknown): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value === "string" && value !== "") {
    return new Date(value).toISOString();
  }
  return null;
}

export function accountView(user: unknown): Record<string, unknown> {
  let reason: string | null = null;
  const stored = field(user, "banReason");
  if (typeof stored === "string" && stored !== "") {
    reason = stored;
  }
  return {
    id: field(user, "id"),
    email: field(user, "email"),
    role: field(user, "role") ?? "user",
    email_verified: field(user, "emailVerified") === true,
    two_factor: field(user, "twoFactorEnabled") === true,
    created_at: isoDate(field(user, "createdAt")),
    banned_at: isoDate(field(user, "bannedAt")),
    ban_reason: reason,
  };
}

function parsed(body: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(body);
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

function userIdOf(body: Record<string, unknown>): string | null {
  const value = body.user_id;
  if (typeof value !== "string" || value === "" || value.length > USER_ID_MAX_CHARS) {
    return null;
  }
  return value;
}

export function banReason(value: unknown): string | null | undefined {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  if ([...trimmed].length > BAN_REASON_MAX_CHARS) {
    return undefined;
  }
  if (trimmed === "") {
    return null;
  }
  return trimmed;
}

async function findAccount(auth: Auth, search: URLSearchParams): Promise<InternalAnswer> {
  const email = (search.get("email") ?? "").trim();
  if (email === "" || email.length > EMAIL_MAX_CHARS || !email.includes("@")) {
    return INVALID;
  }
  const context = await auth.$context;
  const found = await context.internalAdapter.findUserByEmail(email);
  if (found === null) {
    return NOT_FOUND;
  }
  const stored = await context.internalAdapter.findUserById(found.user.id);
  return { status: 200, body: { account: accountView(stored) } };
}

async function ban(auth: Auth, body: string): Promise<InternalAnswer> {
  const values = parsed(body);
  if (values === null) {
    return INVALID;
  }
  const userId = userIdOf(values);
  const reason = banReason(values.reason);
  if (userId === null || reason === undefined) {
    return INVALID;
  }
  const context = await auth.$context;
  const user = await context.internalAdapter.findUserById(userId);
  if (user === null) {
    return NOT_FOUND;
  }
  if (field(user, "role") === ROLE_ADMIN) {
    return IS_ADMIN;
  }
  await context.internalAdapter.updateUser(userId, { bannedAt: new Date(), banReason: reason });
  await context.internalAdapter.deleteUserSessions(userId);
  return DONE;
}

async function unban(auth: Auth, body: string): Promise<InternalAnswer> {
  const values = parsed(body);
  if (values === null) {
    return INVALID;
  }
  const userId = userIdOf(values);
  if (userId === null) {
    return INVALID;
  }
  const context = await auth.$context;
  const user = await context.internalAdapter.findUserById(userId);
  if (user === null) {
    return NOT_FOUND;
  }
  await context.internalAdapter.updateUser(userId, { bannedAt: null, banReason: null });
  return DONE;
}

export function internalRoutes(auth: Auth): (request: InternalRequest) => Promise<InternalAnswer> {
  return async (request) => {
    if (request.method === "GET" && request.path === SESSION_ROUTE) {
      return currentSession(auth, request.cookie);
    }
    if (request.method === "GET" && request.path === ACCOUNTS_ROUTE) {
      return findAccount(auth, request.search);
    }
    if (request.method === "POST" && request.path === BAN_ROUTE) {
      return ban(auth, request.body);
    }
    if (request.method === "POST" && request.path === UNBAN_ROUTE) {
      return unban(auth, request.body);
    }
    return NOT_FOUND;
  };
}
