import { betterAuth, type BetterAuthOptions } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";

import { LIMITER_IP_HEADER } from "./client-ip.ts";
import { ERASE_UNAVAILABLE, type Erase } from "./erase.ts";
import { GUARD_UNAVAILABLE, GUARDED_PATHS, altchaPayload, ipHeaders, type Guard } from "./guard.ts";
import { mailLanguage, type Deposit } from "./outbox.ts";
import { isSecure, type Settings } from "./settings.ts";

export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;
export const COOKIE_PREFIX = "mcplain";
export const BASE_PATH = "/api/auth";
const DELETE_USER_PATH = "/delete-user";
const SIGN_UP_PATH = "/sign-up/email";
export const SIGN_UP_ANSWER = { token: null, user: null } as const;
const ROLE_FIELD = "role";

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
    advanced: {
      cookiePrefix: COOKIE_PREFIX,
      useSecureCookies: isSecure(settings),
      defaultCookieAttributes: { httpOnly: true, sameSite: "lax" as const, secure: isSecure(settings) },
      ipAddress: { ipAddressHeaders: [LIMITER_IP_HEADER], ipv6Subnet: 64 as const },
    },
    rateLimit: { enabled: true, storage: "memory" as const, window: 60, max: 100 },
    databaseHooks: {
      session: {
        create: {
          before: async (session: Record<string, unknown>) => ({ data: { ...session, ipAddress: null, userAgent: null } }),
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
