import { betterAuth, type BetterAuthOptions } from "better-auth";
import { APIError, createAuthMiddleware, getSessionFromCtx } from "better-auth/api";
import { twoFactor } from "better-auth/plugins";

import { LIMITER_IP_HEADER } from "./client-ip.ts";
import { ERASE_UNAVAILABLE, type Erase } from "./erase.ts";
import { GUARD_UNAVAILABLE, GUARDED_PATHS, altchaPayload, ipHeaders, type Guard } from "./guard.ts";
import { mailLanguage, type Deposit } from "./outbox.ts";
import { SESSION_REFUSED, sessionRefusal } from "./session-gate.ts";
import { isSecure, type Settings } from "./settings.ts";

export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;
export const COOKIE_PREFIX = "mcplain";
export const BASE_PATH = "/api/auth";
const DELETE_USER_PATH = "/delete-user";
const SIGN_UP_PATH = "/sign-up/email";
export const RATE_WINDOW_SECONDS = 60;
export const RATE_MAX = 100;
export const SIGN_UP_ANSWER = { token: null, user: null } as const;
const ROLE_FIELD = "role";
const ROLE_ADMIN = "admin";
export const TOTP_ISSUER = "MCPlain";
export const TOTP_DIGITS = 6;
export const TOTP_PERIOD_SECONDS = 30;
export const LOCKOUT_FAILED_ATTEMPTS = 10;
export const LOCKOUT_SECONDS = 900;
const ENABLE_PATH = "/two-factor/enable";
export const TRUST_DEVICE_PATHS: ReadonlySet<string> = new Set(["/two-factor/verify-totp", "/two-factor/verify-backup-code"]);
export const DISABLED_PATHS = ["/two-factor/send-otp", "/two-factor/verify-otp", "/two-factor/get-totp-uri"];
export const TWO_FACTOR_ADMIN_ONLY = "TWO_FACTOR_ADMIN_ONLY";

type SessionHookContext = { path?: string; context: { internalAdapter: { findUserById(id: string): Promise<unknown> } } } | null;

const REFUSALS: Record<string, { status: "FORBIDDEN" | "TOO_MANY_REQUESTS" | "SERVICE_UNAVAILABLE"; code: string }> = {
  altcha_invalid: { status: "FORBIDDEN", code: "ALTCHA_INVALID" },
  signup_limit: { status: "TOO_MANY_REQUESTS", code: "SIGNUP_LIMIT" },
  [GUARD_UNAVAILABLE]: { status: "SERVICE_UNAVAILABLE", code: "GUARD_UNAVAILABLE" },
};

export type Dependencies = {
  database: BetterAuthOptions["database"];
  guard: Guard;
  deposit: Deposit;
  erase: Erase;
};

function refusal(code: string): APIError {
  const known = REFUSALS[code] ?? REFUSALS[GUARD_UNAVAILABLE];
  return new APIError(known.status, { code: known.code, message: "Refused" });
}

function bodyOf(body: unknown): Record<string, unknown> {
  if (typeof body !== "object" || body === null) {
    return {};
  }
  return body as Record<string, unknown>;
}

async function guardedSession(session: Record<string, unknown>, context: SessionHookContext): Promise<{ data: Record<string, unknown> }> {
  if (context === null || typeof session.userId !== "string") {
    throw new APIError("FORBIDDEN", { code: SESSION_REFUSED, message: "Refused" });
  }
  const user = await context.context.internalAdapter.findUserById(session.userId);
  const refused = sessionRefusal(user, context.path);
  if (refused !== null) {
    throw new APIError("FORBIDDEN", { code: refused, message: "Refused" });
  }
  return { data: { ...session, ipAddress: null, userAgent: null } };
}

function hasPassword(body: unknown): boolean {
  if (typeof body !== "object" || body === null || !("password" in body)) {
    return false;
  }
  return typeof body.password === "string" && body.password !== "";
}

export function authOptions(settings: Settings, dependencies: Dependencies) {
  return {
    appName: "MCPlain",
    baseURL: settings.publicUrl,
    basePath: BASE_PATH,
    secret: settings.secret,
    database: dependencies.database,
    trustedOrigins: [settings.publicUrl],
    telemetry: { enabled: false },
    logger: { level: "warn" as const },
    emailAndPassword: {
      enabled: true,
      minPasswordLength: MIN_PASSWORD_LENGTH,
      maxPasswordLength: MAX_PASSWORD_LENGTH,
      requireEmailVerification: true,
      autoSignIn: false,
      revokeSessionsOnPasswordReset: true,
      sendResetPassword: async ({ user, url }: { user: { email: string }; url: string }, request?: Request) => {
        await dependencies.deposit({ kind: "reset_password", lang: mailLanguage(request), recipient: user.email, link: url });
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      sendOnSignIn: true,
      autoSignInAfterVerification: true,
      sendVerificationEmail: async ({ user, url }: { user: { email: string }; url: string }, request?: Request) => {
        await dependencies.deposit({ kind: "verify_email", lang: mailLanguage(request), recipient: user.email, link: url });
      },
    },
    user: {
      additionalFields: {
        [ROLE_FIELD]: { type: ["user", "admin", "bench"] as const, required: false, defaultValue: "user", input: false },
        bannedAt: { type: "date" as const, required: false, input: false, returned: false },
        banReason: { type: "string" as const, required: false, input: false, returned: false },
      },
      deleteUser: {
        enabled: true,
        beforeDelete: async (user: { id: string }) => {
          if (!(await dependencies.erase(user.id))) {
            throw new APIError("SERVICE_UNAVAILABLE", { code: ERASE_UNAVAILABLE, message: "Refused" });
          }
        },
      },
    },
    account: { accountLinking: { enabled: false } },
    disabledPaths: DISABLED_PATHS,
    plugins: [
      twoFactor({
        issuer: TOTP_ISSUER,
        totpOptions: { digits: TOTP_DIGITS, period: TOTP_PERIOD_SECONDS },
        accountLockout: { enabled: true, maxFailedAttempts: LOCKOUT_FAILED_ATTEMPTS, durationSeconds: LOCKOUT_SECONDS },
      }),
    ],
    advanced: {
      cookiePrefix: COOKIE_PREFIX,
      useSecureCookies: isSecure(settings),
      defaultCookieAttributes: { httpOnly: true, sameSite: "lax" as const, secure: isSecure(settings) },
      ipAddress: { ipAddressHeaders: [LIMITER_IP_HEADER], ipv6Subnet: 64 as const },
    },
    rateLimit: { enabled: true, storage: "memory" as const, window: RATE_WINDOW_SECONDS, max: RATE_MAX },
    databaseHooks: {
      session: {
        create: {
          before: async (session: Record<string, unknown>, context: SessionHookContext) => guardedSession(session, context),
        },
        update: {
          before: async (session: Record<string, unknown>) => ({ data: { ...session, ipAddress: null, userAgent: null } }),
        },
      },
    },
    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        if (ctx.path === DELETE_USER_PATH && !hasPassword(ctx.body)) {
          throw new APIError("BAD_REQUEST", { code: "PASSWORD_REQUIRED", message: "Password required" });
        }
        if (ctx.path === ENABLE_PATH) {
          const current = await getSessionFromCtx(ctx);
          if (current === null || (current.user as Record<string, unknown>)[ROLE_FIELD] !== ROLE_ADMIN) {
            throw new APIError("FORBIDDEN", { code: TWO_FACTOR_ADMIN_ONLY, message: "Refused" });
          }
          return { context: { body: { ...bodyOf(ctx.body), method: "totp", issuer: TOTP_ISSUER } } };
        }
        if (TRUST_DEVICE_PATHS.has(ctx.path)) {
          return { context: { body: { ...bodyOf(ctx.body), trustDevice: false } } };
        }
        const action = GUARDED_PATHS[ctx.path];
        if (action === undefined) {
          return;
        }
        const answer = await dependencies.guard(action, altchaPayload(ctx.headers), ipHeaders(ctx.headers));
        if (!answer.ok) {
          throw refusal(answer.code);
        }
      }),
      after: createAuthMiddleware(async (ctx) => {
        if (ctx.path !== SIGN_UP_PATH || ctx.context.returned instanceof APIError) {
          return;
        }
        return ctx.json(SIGN_UP_ANSWER);
      }),
    },
  } satisfies BetterAuthOptions;
}

export function createAuth(settings: Settings, dependencies: Dependencies) {
  return betterAuth(authOptions(settings, dependencies));
}
