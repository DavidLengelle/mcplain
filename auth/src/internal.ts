import type { createAuth } from "./auth.ts";

export type Auth = ReturnType<typeof createAuth>;

export type InternalRequest = { method: string; path: string; search: URLSearchParams; cookie: string | undefined; body: string };

export type InternalAnswer = { status: number; body: unknown };

export const INTERNAL_PREFIX = "/internal/";
export const SESSION_ROUTE = "/internal/session";
export const INTERNAL_BODY_MAX_BYTES = 2048;
const COOKIE_MAX_CHARS = 8192;

const NOT_FOUND: InternalAnswer = { status: 404, body: { error: "not_found" } };

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

export function internalRoutes(auth: Auth): (request: InternalRequest) => Promise<InternalAnswer> {
  return async (request) => {
    if (request.method === "GET" && request.path === SESSION_ROUTE) {
      return currentSession(auth, request.cookie);
    }
    return NOT_FOUND;
  };
}
