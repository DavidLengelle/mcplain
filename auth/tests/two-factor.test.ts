import { memoryAdapter } from "better-auth/adapters/memory";
import { describe, expect, it } from "vitest";

import { authOptions, createAuth, DISABLED_PATHS, LOCKOUT_FAILED_ATTEMPTS, LOCKOUT_SECONDS, TOTP_DIGITS, TOTP_ISSUER, TOTP_PERIOD_SECONDS } from "../src/auth.ts";
import { LIMITER_IP_HEADER } from "../src/client-ip.ts";
import { dropTrustDevice, withoutTrustDevice } from "../src/cookies.ts";
import type { Mail } from "../src/outbox.ts";
import { sessionRefusal, TWO_FACTOR_SESSION_PATHS } from "../src/session-gate.ts";
import type { Settings } from "../src/settings.ts";
import { secretOf, totpCode, wrongCode } from "./totp.ts";

const ORIGIN = "http://localhost:3010";
const PASSWORD = "a long enough password";
const SETTINGS: Settings = {
  databaseUrl: "postgres://unused",
  secret: "test only secret, never a real one, 0123456789",
  publicUrl: ORIGIN,
  apiUrl: "http://api:8000",
  trustedProxyHops: 1,
  port: 3100,
  internalPeers: ["api"],
};

type Row = Record<string, unknown>;
type Tables = { user: Row[]; session: Row[]; account: Row[]; verification: Row[]; twoFactor: Row[] };

let visitor = 0;

function nextVisitor(): string {
  visitor += 1;
  return `203.0.113.${visitor % 250}`;
}

function setup() {
  const tables: Tables = { user: [], session: [], account: [], verification: [], twoFactor: [] };
  const mails: Mail[] = [];
  const auth = createAuth(SETTINGS, {
    database: memoryAdapter(tables),
    guard: async () => ({ ok: true }),
    deposit: async (mail) => void mails.push(mail),
    erase: async () => true,
  });
  return { auth, tables, mails };
}

type Auth = ReturnType<typeof setup>["auth"];

function post(path: string, body: unknown, cookie: string = ""): Request {
  const headers: Record<string, string> = { "Content-Type": "application/json", Origin: ORIGIN, "x-altcha": "PAYLOAD", [LIMITER_IP_HEADER]: nextVisitor() };
  if (cookie !== "") {
    headers.Cookie = cookie;
  }
  return new Request(`${ORIGIN}/api/auth${path}`, { method: "POST", headers, body: JSON.stringify(body) });
}

function cookiesOf(response: Response): Map<string, string> {
  const found = new Map<string, string>();
  for (const item of response.headers.getSetCookie()) {
    const pair = item.split(";")[0] ?? "";
    const [name = "", ...rest] = pair.split("=");
    found.set(name, rest.join("="));
  }
  return found;
}

function header(cookies: Map<string, string>): string {
  return [...cookies].filter(([, value]) => value !== "").map(([name, value]) => `${name}=${value}`).join("; ");
}

function sessionOf(response: Response): string {
  const value = cookiesOf(response).get("mcplain.session_token") ?? "";
  if (value === "") {
    return "";
  }
  return `mcplain.session_token=${value}`;
}

async function userOf(auth: Auth, cookie: string): Promise<Row | null> {
  const answer = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie, [LIMITER_IP_HEADER]: nextVisitor() } }));
  const body = (await answer.json()) as { user?: Row } | null;
  return body?.user ?? null;
}

async function signUp(auth: Auth, mails: Mail[], tables: Tables, email: string, role: string): Promise<string> {
  await auth.handler(post("/sign-up/email", { email, password: PASSWORD, name: "" }));
  const link = mails.filter((mail) => mail.recipient === email).at(-1)?.link ?? "";
  const cookie = sessionOf(await auth.handler(new Request(link, { headers: { Origin: ORIGIN } })));
  const row = tables.user.find((item) => item.email === email);
  if (row !== undefined) {
    row.role = role;
  }
  return cookie;
}

async function enroll(auth: Auth, cookie: string): Promise<{ secret: string; backupCodes: string[]; cookie: string; uri: string }> {
  const enabled = await auth.handler(post("/two-factor/enable", { password: PASSWORD }, cookie));
  expect(enabled.status).toBe(200);
  const body = (await enabled.json()) as { totpURI: string; backupCodes: string[] };
  const secret = secretOf(body.totpURI);
  const verified = await auth.handler(post("/two-factor/verify-totp", { code: totpCode(secret) }, cookie));
  expect(verified.status).toBe(200);
  return { secret, backupCodes: body.backupCodes, cookie: sessionOf(verified), uri: body.totpURI };
}

async function adminWithTwoFactor(email: string = "boss@example.com") {
  const context = setup();
  const first = await signUp(context.auth, context.mails, context.tables, email, "admin");
  const enrolled = await enroll(context.auth, first);
  return { ...context, ...enrolled, email };
}

function sessionsOf(tables: Tables, email: string): Row[] {
  const user = tables.user.find((item) => item.email === email);
  return tables.session.filter((item) => item.userId === user?.id);
}

async function passwordStep(auth: Auth, email: string): Promise<{ response: Response; challenge: string }> {
  const response = await auth.handler(post("/sign-in/email", { email, password: PASSWORD }));
  return { response, challenge: header(cookiesOf(response)) };
}

describe("the second factor of the admin", () => {
  it("is the twoFactor plugin with the MCPlain issuer, 6 digits, 30 seconds, the lockout on, and no mail or URI route", () => {
    const options = authOptions(SETTINGS, { database: undefined, guard: async () => ({ ok: true }), deposit: async () => {}, erase: async () => true });
    const plugin = options.plugins[0] as unknown as { id: string; options: Record<string, unknown> };
    expect(plugin.id).toBe("two-factor");
    expect(plugin.options).toMatchObject({
      issuer: "MCPlain",
      totpOptions: { digits: 6, period: 30 },
      accountLockout: { enabled: true, maxFailedAttempts: 10, durationSeconds: 900 },
    });
    expect([TOTP_ISSUER, TOTP_DIGITS, TOTP_PERIOD_SECONDS, LOCKOUT_FAILED_ATTEMPTS, LOCKOUT_SECONDS]).toEqual(["MCPlain", 6, 30, 10, 900]);
    expect(plugin.options).not.toHaveProperty("otpOptions");
    expect(plugin.options).not.toHaveProperty("skipVerificationOnEnable");
    expect(plugin.options).not.toHaveProperty("allowPasswordless");
    expect(options.disabledPaths).toEqual(DISABLED_PATHS);
  });

  it("is offered to the admin role only", async () => {
    const { auth, mails, tables } = setup();
    const cookie = await signUp(auth, mails, tables, "ada@example.com", "user");
    const refused = await auth.handler(post("/two-factor/enable", { password: PASSWORD }, cookie));
    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({ code: "TWO_FACTOR_ADMIN_ONLY" });
    const bench = await signUp(auth, mails, tables, "bench@example.com", "bench");
    expect((await auth.handler(post("/two-factor/enable", { password: PASSWORD }, bench))).status).toBe(403);
    expect((await auth.handler(post("/two-factor/enable", { password: PASSWORD }))).status).toBe(403);
    expect(tables.twoFactor).toEqual([]);
  });

  it("asks the password, gives a key to type with the MCPlain issuer, and turns on only after a first code", async () => {
    const { auth, mails, tables } = setup();
    const cookie = await signUp(auth, mails, tables, "boss@example.com", "admin");
    expect((await auth.handler(post("/two-factor/enable", { password: "a wrong password" }, cookie))).status).toBe(400);
    const enabled = await auth.handler(post("/two-factor/enable", { password: PASSWORD, issuer: "Evil", method: "otp" }, cookie));
    const body = (await enabled.json()) as { totpURI: string; backupCodes: string[] };
    const uri = new URL(body.totpURI);
    expect(uri.searchParams.get("issuer")).toBe("MCPlain");
    expect(uri.searchParams.get("digits")).toBe("6");
    expect(uri.searchParams.get("period")).toBe("30");
    expect(secretOf(body.totpURI)).toMatch(/^[A-Z2-7]+=*$/);
    expect(body.backupCodes).toHaveLength(10);
    expect((await userOf(auth, cookie))?.twoFactorEnabled).toBe(false);
    expect(JSON.stringify(tables.twoFactor)).not.toContain(secretOf(body.totpURI));
    const wrong = await auth.handler(post("/two-factor/verify-totp", { code: wrongCode(secretOf(body.totpURI)) }, cookie));
    expect(wrong.status).toBe(401);
    const right = await auth.handler(post("/two-factor/verify-totp", { code: totpCode(secretOf(body.totpURI)) }, cookie));
    expect(right.status).toBe(200);
    expect((await userOf(auth, sessionOf(right)))?.twoFactorEnabled).toBe(true);
  });

  it("gives no session for the password alone, and one for the password and a right code", async () => {
    const { auth, tables, secret, email } = await adminWithTwoFactor();
    tables.session.length = 0;
    const { response, challenge } = await passwordStep(auth, email);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ twoFactorRedirect: true, twoFactorMethods: ["totp"] });
    expect(sessionOf(response)).toBe("");
    expect(sessionsOf(tables, email)).toEqual([]);
    const wrong = await auth.handler(post("/two-factor/verify-totp", { code: wrongCode(secret) }, challenge));
    expect(wrong.status).toBe(401);
    expect(sessionsOf(tables, email)).toEqual([]);
    const right = await auth.handler(post("/two-factor/verify-totp", { code: totpCode(secret) }, challenge));
    expect(right.status).toBe(200);
    expect(sessionsOf(tables, email)).toHaveLength(1);
    expect((await userOf(auth, sessionOf(right)))?.email).toBe(email);
  });

  it("locks the account for 15 minutes after 10 wrong codes in a row, even with the right code after", async () => {
    const { auth, tables, secret, email } = await adminWithTwoFactor();
    for (let round = 0; round < 2; round += 1) {
      const { challenge } = await passwordStep(auth, email);
      for (let attempt = 0; attempt < 5; attempt += 1) {
        expect((await auth.handler(post("/two-factor/verify-totp", { code: wrongCode(secret) }, challenge))).status).toBe(401);
      }
    }
    const { challenge } = await passwordStep(auth, email);
    const locked = await auth.handler(post("/two-factor/verify-totp", { code: totpCode(secret) }, challenge));
    expect(locked.status).toBe(429);
    expect(await locked.json()).toMatchObject({ code: "ACCOUNT_TEMPORARILY_LOCKED" });
    const lockedUntil = tables.twoFactor[0]?.lockedUntil as Date;
    expect(lockedUntil.getTime() - Date.now()).toBeGreaterThan(14 * 60 * 1000);
  });

  it("accepts a backup code once only", async () => {
    const { auth, backupCodes, email, tables } = await adminWithTwoFactor();
    const code = backupCodes[0] ?? "";
    const first = await passwordStep(auth, email);
    const used = await auth.handler(post("/two-factor/verify-backup-code", { code }, first.challenge));
    expect(used.status).toBe(200);
    expect(sessionOf(used)).not.toBe("");
    const second = await passwordStep(auth, email);
    const again = await auth.handler(post("/two-factor/verify-backup-code", { code }, second.challenge));
    expect(again.status).toBe(401);
    expect(JSON.stringify(tables.twoFactor)).not.toContain(code);
  });

  it("regenerates the backup codes with the password only, and the old ones stop working", async () => {
    const { auth, backupCodes, cookie, email } = await adminWithTwoFactor();
    expect((await auth.handler(post("/two-factor/generate-backup-codes", { password: "a wrong password" }, cookie))).status).toBe(400);
    const fresh = await auth.handler(post("/two-factor/generate-backup-codes", { password: PASSWORD }, cookie));
    const codes = ((await fresh.json()) as { backupCodes: string[] }).backupCodes;
    expect(codes).toHaveLength(10);
    const old = await passwordStep(auth, email);
    expect((await auth.handler(post("/two-factor/verify-backup-code", { code: backupCodes[1] }, old.challenge))).status).toBe(401);
    const next = await passwordStep(auth, email);
    expect((await auth.handler(post("/two-factor/verify-backup-code", { code: codes[0] }, next.challenge))).status).toBe(200);
  });

  it("never trusts a device: trustDevice sent anyway sets no cookie, and the next sign-in asks the code again", async () => {
    const { auth, secret, email } = await adminWithTwoFactor();
    const { challenge } = await passwordStep(auth, email);
    const verified = await auth.handler(post("/two-factor/verify-totp", { code: totpCode(secret), trustDevice: true }, challenge));
    expect(verified.status).toBe(200);
    const set = cookiesOf(verified);
    expect([...set.keys()].filter((name) => name.includes("trust_device") && set.get(name) !== "")).toEqual([]);
    const again = await passwordStep(auth, email);
    expect(await again.response.json()).toMatchObject({ twoFactorRedirect: true });
    expect(sessionOf(again.response)).toBe("");
  });

  it("drops a trust_device cookie sent by the browser before Better Auth reads the request", () => {
    expect(withoutTrustDevice("mcplain.session_token=a; mcplain.trust_device=b; theme=dark")).toBe("mcplain.session_token=a; theme=dark");
    expect(withoutTrustDevice("__Secure-mcplain.trust_device=b")).toBe("");
    const headers: Record<string, string> = { cookie: "mcplain.trust_device=b" };
    dropTrustDevice(headers);
    expect(headers).toEqual({});
  });

  it("removes the admin power when turned off with the password, and the key is gone", async () => {
    const { auth, cookie, tables } = await adminWithTwoFactor();
    expect((await auth.handler(post("/two-factor/disable", { password: "a wrong password" }, cookie))).status).toBe(400);
    const off = await auth.handler(post("/two-factor/disable", { password: PASSWORD }, cookie));
    expect(off.status).toBe(200);
    expect((await userOf(auth, sessionOf(off)))?.twoFactorEnabled).toBe(false);
    expect(tables.twoFactor).toEqual([]);
  });

  it("answers 404 to the routes that would send a code by mail or show the key again", async () => {
    const { auth, cookie } = await adminWithTwoFactor();
    for (const path of DISABLED_PATHS) {
      expect((await auth.handler(post(path, { password: PASSWORD }, cookie))).status).toBe(404);
    }
  });
});

describe("every route that makes a session", () => {
  it("keeps one list of exceptions for an account with the second factor", () => {
    expect([...TWO_FACTOR_SESSION_PATHS].sort()).toEqual([
      "/change-password",
      "/sign-in/email",
      "/two-factor/disable",
      "/two-factor/enable",
      "/two-factor/verify-backup-code",
      "/two-factor/verify-totp",
    ]);
  });

  it("refuses when in doubt: no context, unknown route, unknown user, or a strange second factor value", () => {
    const admin = { id: "a", twoFactorEnabled: true, bannedAt: null };
    expect(sessionRefusal(admin, undefined)).toBe("TWO_FACTOR_REQUIRED");
    expect(sessionRefusal(admin, "/verify-email")).toBe("TWO_FACTOR_REQUIRED");
    expect(sessionRefusal(admin, "/sign-in/social")).toBe("TWO_FACTOR_REQUIRED");
    expect(sessionRefusal({ ...admin, twoFactorEnabled: "yes" }, "/verify-email")).toBe("TWO_FACTOR_REQUIRED");
    expect(sessionRefusal(admin, "/two-factor/verify-totp")).toBeNull();
    expect(sessionRefusal(null, "/sign-in/email")).toBe("SESSION_REFUSED");
    expect(sessionRefusal({ id: "u", twoFactorEnabled: false }, "/verify-email")).toBeNull();
  });

  it("never gives an admin session from the mail link, even once the address is no longer verified", async () => {
    const { auth, mails, tables, email } = await adminWithTwoFactor();
    const row = tables.user.find((item) => item.email === email);
    if (row !== undefined) {
      row.emailVerified = false;
    }
    tables.session.length = 0;
    const early = await passwordStep(auth, email);
    expect(early.response.status).toBe(403);
    const link = mails.filter((mail) => mail.recipient === email && mail.kind === "verify_email").at(-1)?.link ?? "";
    expect(link).not.toBe("");
    const clicked = await auth.handler(new Request(link, { headers: { Origin: ORIGIN } }));
    expect(clicked.status).toBe(403);
    expect(sessionOf(clicked)).toBe("");
    expect(sessionsOf(tables, email)).toEqual([]);
  });

  it("never gives a session from a password reset", async () => {
    const { auth, mails, tables, email } = await adminWithTwoFactor();
    tables.session.length = 0;
    await auth.handler(post("/request-password-reset", { email, redirectTo: "/en/account/new-password" }));
    const link = mails.filter((mail) => mail.kind === "reset_password").at(-1)?.link ?? "";
    const token = new URL(link).pathname.split("/").at(-1) ?? "";
    const reset = await auth.handler(post("/reset-password", { token, newPassword: "another long password" }));
    expect(reset.status).toBe(200);
    expect(sessionOf(reset)).toBe("");
    expect(sessionsOf(tables, email)).toEqual([]);
    const signIn = await auth.handler(post("/sign-in/email", { email, password: "another long password" }));
    expect(await signIn.json()).toMatchObject({ twoFactorRedirect: true });
    expect(sessionsOf(tables, email)).toEqual([]);
  });
});
