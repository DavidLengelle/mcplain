import { memoryAdapter } from "better-auth/adapters/memory";
import { describe, expect, it, vi } from "vitest";

import { authOptions, createAuth, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "../src/auth.ts";
import { limiterAddress, LIMITER_IP_HEADER, setLimiterAddress } from "../src/client-ip.ts";
import { apiErase } from "../src/erase.ts";
import { apiGuard, type Guard, type GuardAction } from "../src/guard.ts";
import { mailLanguage, outboxDeposit, type Mail } from "../src/outbox.ts";
import { readSettings, type Settings } from "../src/settings.ts";

const TEST_SECRET = "test only secret, never a real one, 0123456789";
const ORIGIN = "http://localhost:3010";
const PASSWORD = "a long enough password";

const SETTINGS: Settings = {
  databaseUrl: "postgres://unused",
  secret: TEST_SECRET,
  publicUrl: ORIGIN,
  apiUrl: "http://api:8000",
  trustedProxyHops: 1,
  port: 3100,
};

type Body = { code?: string; user?: { role?: string } };

async function bodyOf(response: Response): Promise<Body> {
  return (await response.json()) as Body;
}

type Call = { action: GuardAction; altcha: string | null; headers: Record<string, string> };

function setup(
  answer: (action: GuardAction) => { ok: true } | { ok: false; code: string } = () => ({ ok: true }),
  erased: boolean = true,
) {
  const calls: Call[] = [];
  const mails: Mail[] = [];
  const erasures: string[] = [];
  const guard: Guard = async (action, altcha, headers) => {
    calls.push({ action, altcha, headers });
    return answer(action);
  };
  const erase = async (userId: string) => {
    erasures.push(userId);
    return erased;
  };
  const database = memoryAdapter({ user: [], session: [], account: [], verification: [] });
  const auth = createAuth(SETTINGS, { database, guard, deposit: async (mail) => void mails.push(mail), erase });
  return { auth, calls, mails, erasures };
}

let visitor = 0;

function nextVisitor(): string {
  visitor += 1;
  return `198.51.100.${visitor % 250}`;
}

function post(path: string, body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`${ORIGIN}/api/auth${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: ORIGIN, "x-altcha": "PAYLOAD", [LIMITER_IP_HEADER]: nextVisitor(), ...headers },
    body: JSON.stringify(body),
  });
}

function sessionCookie(response: Response): string {
  return response.headers
    .getSetCookie()
    .map((item) => item.split(";")[0] ?? "")
    .filter((item) => item.startsWith("mcplain."))
    .join("; ");
}

async function signUpAndVerify(auth: ReturnType<typeof setup>["auth"], mails: Mail[], email: string): Promise<string> {
  await auth.handler(post("/sign-up/email", { email, password: PASSWORD, name: "" }, { "x-mcplain-lang": "fr" }));
  const link = mails.filter((mail) => mail.kind === "verify_email").at(-1)?.link ?? "";
  const verified = await auth.handler(new Request(link, { headers: { Origin: ORIGIN } }));
  return sessionCookie(verified);
}

describe("settings of the counter", () => {
  it("reads every setting and refuses a missing or short secret", () => {
    const env = {
      BETTER_AUTH_SECRET: TEST_SECRET,
      MCPLAIN_GUICHET_DATABASE_URL: "postgres://mcplain_guichet@postgres/mcplain",
      MCPLAIN_PUBLIC_URL: "http://localhost:3010/",
    };
    expect(readSettings(env)).toEqual({
      databaseUrl: "postgres://mcplain_guichet@postgres/mcplain",
      secret: TEST_SECRET,
      publicUrl: ORIGIN,
      apiUrl: "http://api:8000",
      trustedProxyHops: 1,
      port: 3100,
    });
    expect(() => readSettings({ ...env, BETTER_AUTH_SECRET: "" })).toThrow(/init-secrets/);
    expect(() => readSettings({ ...env, BETTER_AUTH_SECRET: "short" })).toThrow(/32/);
    expect(() => readSettings({ ...env, MCPLAIN_PUBLIC_URL: "ftp://x" })).toThrow();
    expect(() => readSettings({ ...env, MCPLAIN_TRUSTED_PROXY_HOPS: "9" })).toThrow();
  });

  it("sets Better Auth as decided: email and password only, verified email, cookies, limiter, no telemetry", () => {
    const options = authOptions(SETTINGS, { database: undefined, guard: async () => ({ ok: true }), deposit: async () => {}, erase: async () => true });
    expect(options.emailAndPassword).toMatchObject({
      enabled: true,
      minPasswordLength: MIN_PASSWORD_LENGTH,
      maxPasswordLength: MAX_PASSWORD_LENGTH,
      requireEmailVerification: true,
    });
    expect([MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH]).toEqual([10, 128]);
    expect(options.emailVerification).toMatchObject({ sendOnSignUp: true, autoSignInAfterVerification: true });
    expect(options.user.deleteUser.enabled).toBe(true);
    expect(options.user.additionalFields.role).toMatchObject({ input: false, defaultValue: "user", type: ["user", "admin", "bench"] });
    expect(options.trustedOrigins).toEqual([ORIGIN]);
    expect(options.baseURL).toBe(ORIGIN);
    expect(options.advanced).toMatchObject({
      cookiePrefix: "mcplain",
      useSecureCookies: false,
      defaultCookieAttributes: { httpOnly: true, sameSite: "lax", secure: false },
    });
    expect(options.rateLimit.enabled).toBe(true);
    expect(options.rateLimit.customRules).toEqual({ "/get-session": false });
    expect(options.telemetry.enabled).toBe(false);
    expect(options).not.toHaveProperty("socialProviders");
    expect(options).not.toHaveProperty("plugins");
    const secure = authOptions({ ...SETTINGS, publicUrl: "https://mcplain.example" }, {
      database: undefined,
      guard: async () => ({ ok: true }),
      deposit: async () => {},
      erase: async () => true,
    });
    expect(secure.advanced.useSecureCookies).toBe(true);
    expect(secure.advanced.defaultCookieAttributes.secure).toBe(true);
  });
});

describe("the guard hook", () => {
  it("asks the API before a sign-up, with the ALTCHA payload and the raw address headers", async () => {
    const { auth, calls } = setup();
    await auth.handler(post("/sign-up/email", { email: "ada@example.com", password: PASSWORD, name: "" }, { "x-forwarded-for": "6.6.6.6, 203.0.113.7" }));
    expect(calls).toEqual([{ action: "sign_up", altcha: "PAYLOAD", headers: { "x-forwarded-for": "6.6.6.6, 203.0.113.7" } }]);
  });

  it("guards the sign-in and the password reset, and nothing else", async () => {
    const { auth, calls } = setup();
    await auth.handler(post("/sign-in/email", { email: "ada@example.com", password: PASSWORD }));
    await auth.handler(post("/request-password-reset", { email: "ada@example.com", redirectTo: "/fr/compte/nouveau-mot-de-passe" }));
    await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`));
    expect(calls.map((call) => call.action)).toEqual(["sign_in", "request_password_reset"]);
  });

  it("refuses with a clear code and creates nothing", async () => {
    const { auth, mails } = setup(() => ({ ok: false, code: "signup_limit" }));
    const response = await auth.handler(post("/sign-up/email", { email: "ada@example.com", password: PASSWORD, name: "" }));
    expect(response.status).toBe(429);
    expect(await response.json()).toMatchObject({ code: "SIGNUP_LIMIT", message: "Refused" });
    expect(mails).toEqual([]);
    const bad = setup(() => ({ ok: false, code: "altcha_invalid" }));
    const refused = await bad.auth.handler(post("/sign-in/email", { email: "ada@example.com", password: PASSWORD }));
    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({ code: "ALTCHA_INVALID" });
  });

  it("refuses when the API does not answer", async () => {
    const guard = apiGuard("http://api:8000", vi.fn(async () => {
      throw new Error("down");
    }));
    expect(await guard("sign_in", "x", {})).toEqual({ ok: false, code: "guard_unavailable" });
    const strange = apiGuard("http://api:8000", vi.fn(async () => new Response('{"code":"anything"}', { status: 403 })));
    expect(await strange("sign_in", "x", {})).toEqual({ ok: false, code: "guard_unavailable" });
    const fetcher = vi.fn(async () => new Response('{"ok":false,"code":"signup_limit"}', { status: 429 }));
    expect(await apiGuard("http://api:8000", fetcher)("sign_up", "x", { "x-forwarded-for": "1.2.3.4" })).toEqual({ ok: false, code: "signup_limit" });
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api:8000/internal/auth-guard");
    expect(JSON.parse(String(init.body))).toEqual({ action: "sign_up", altcha: "x", ip_headers: { "x-forwarded-for": "1.2.3.4" } });
  });
});

describe("accounts", () => {
  it("leaves the verification mail in the outbox, refuses the sign-in before verification, signs in after it", async () => {
    const { auth, mails } = setup();
    const signUp = await auth.handler(post("/sign-up/email", { email: "Ada@Example.com", password: PASSWORD, name: "" }, { "x-mcplain-lang": "fr" }));
    expect(signUp.status).toBe(200);
    expect(sessionCookie(signUp)).toBe("");
    expect(mails).toHaveLength(1);
    expect(mails[0]).toMatchObject({ kind: "verify_email", lang: "fr", recipient: "ada@example.com" });
    expect(mails[0]?.link.startsWith(`${ORIGIN}/api/auth/verify-email?token=`)).toBe(true);
    const early = await auth.handler(post("/sign-in/email", { email: "ada@example.com", password: PASSWORD }));
    expect(early.status).toBe(403);
    const cookie = await signUpAndVerify(auth, mails, "ada@example.com");
    expect(cookie).toMatch(/^mcplain\.session_token=/);
    const session = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie } }));
    expect(await session.json()).toMatchObject({ user: { email: "ada@example.com", emailVerified: true, role: "user" } });
  });

  it("does not tell whether an email already has an account", async () => {
    const { auth, mails } = setup();
    await signUpAndVerify(auth, mails, "ada@example.com");
    const mailsBefore = mails.length;
    const again = await auth.handler(post("/sign-up/email", { email: "ada@example.com", password: PASSWORD, name: "" }));
    const fresh = await auth.handler(post("/sign-up/email", { email: "grace@example.com", password: PASSWORD, name: "" }));
    expect([again.status, fresh.status]).toEqual([200, 200]);
    expect(await again.text()).toBe(await fresh.text());
    expect(sessionCookie(again)).toBe(sessionCookie(fresh));
    expect(mails.slice(mailsBefore).map((mail) => mail.recipient)).toEqual(["grace@example.com"]);
    const wrong = await auth.handler(post("/sign-in/email", { email: "ada@example.com", password: "a wrong password" }));
    const unknown = await auth.handler(post("/sign-in/email", { email: "nobody@example.com", password: PASSWORD }));
    expect([wrong.status, unknown.status]).toEqual([401, 401]);
    expect((await bodyOf(wrong)).code).toBe((await bodyOf(unknown)).code);
  });

  it("refuses passwords shorter than 10 or longer than 128 characters", async () => {
    const { auth } = setup();
    const short = await auth.handler(post("/sign-up/email", { email: "a@example.com", password: "123456789", name: "" }));
    const long = await auth.handler(post("/sign-up/email", { email: "b@example.com", password: "x".repeat(129), name: "" }));
    expect([short.status, long.status]).toEqual([400, 400]);
  });

  it("sends the reset link to the outbox and answers the same for an unknown email", async () => {
    const { auth, mails } = setup();
    await signUpAndVerify(auth, mails, "ada@example.com");
    const known = await auth.handler(post("/request-password-reset", { email: "ada@example.com", redirectTo: "/en/account/new-password" }, { "x-mcplain-lang": "en" }));
    const unknown = await auth.handler(post("/request-password-reset", { email: "nobody@example.com", redirectTo: "/en/account/new-password" }));
    expect([known.status, unknown.status]).toEqual([200, 200]);
    const resets = mails.filter((mail) => mail.kind === "reset_password");
    expect(resets).toHaveLength(1);
    expect(resets[0]).toMatchObject({ lang: "en", recipient: "ada@example.com" });
  });

  it("never lets the website change the role", async () => {
    const { auth, mails } = setup();
    await auth.handler(post("/sign-up/email", { email: "eve@example.com", password: PASSWORD, name: "", role: "admin" }));
    const eveLink = mails.find((mail) => mail.recipient === "eve@example.com")?.link ?? "";
    const eveCookie = sessionCookie(await auth.handler(new Request(eveLink, { headers: { Origin: ORIGIN } })));
    const eve = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: eveCookie } }));
    expect((await bodyOf(eve)).user?.role).toBe("user");
    const cookie = await signUpAndVerify(auth, mails, "ada@example.com");
    const update = await auth.handler(post("/update-user", { role: "admin" }, { Cookie: cookie }));
    expect(update.status).toBe(400);
    const session = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie } }));
    expect((await bodyOf(session)).user?.role).toBe("user");
  });

  it("deletes an account only with its password, after the API erased its history and its quotas", async () => {
    const { auth, mails, erasures } = setup();
    const cookie = await signUpAndVerify(auth, mails, "ada@example.com");
    const session = await bodyOf(await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie } })));
    const without = await auth.handler(post("/delete-user", {}, { Cookie: cookie }));
    expect(without.status).toBe(400);
    const wrong = await auth.handler(post("/delete-user", { password: "a wrong password" }, { Cookie: cookie }));
    expect(wrong.status).toBe(400);
    expect(erasures).toEqual([]);
    const done = await auth.handler(post("/delete-user", { password: PASSWORD }, { Cookie: cookie }));
    expect(done.status).toBe(200);
    expect(erasures).toEqual([(session as { user: { id: string } }).user.id]);
    const signIn = await auth.handler(post("/sign-in/email", { email: "ada@example.com", password: PASSWORD }));
    expect(signIn.status).toBe(401);
  });

  it("keeps the account when the API cannot erase its history, with a code to try again", async () => {
    const { auth, mails, erasures } = setup(() => ({ ok: true }), false);
    const cookie = await signUpAndVerify(auth, mails, "ada@example.com");
    const refused = await auth.handler(post("/delete-user", { password: PASSWORD }, { Cookie: cookie }));
    expect(refused.status).toBe(503);
    expect((await bodyOf(refused)).code).toBe("ERASE_UNAVAILABLE");
    expect(erasures).toHaveLength(1);
    const signIn = await auth.handler(post("/sign-in/email", { email: "ada@example.com", password: PASSWORD }));
    expect(signIn.status).toBe(200);
  });

  it("asks the API to erase through its internal route, and says no when it does not answer 200", async () => {
    const sent: { url: string; body: string }[] = [];
    const statuses = [200, 500];
    const fetcher = async (url: string | URL | Request, init?: RequestInit) => {
      sent.push({ url: String(url), body: String(init?.body) });
      return new Response("{}", { status: statuses[sent.length - 1] });
    };
    const erase = apiErase("http://api:8000", fetcher as typeof fetch);
    expect(await erase("u1")).toBe(true);
    expect(await erase("u1")).toBe(false);
    expect(sent[0]).toEqual({ url: "http://api:8000/internal/account-erase", body: '{"user_id":"u1"}' });
    const down = apiErase("http://api:8000", (async () => {
      throw new TypeError("down");
    }) as typeof fetch);
    expect(await down("u1")).toBe(false);
  });

  it("never limits the reading of a session: the API asks it for every visitor, from one address", async () => {
    const { auth, mails } = setup();
    const cookie = await signUpAndVerify(auth, mails, "ada@example.com");
    const statuses = new Set<number>();
    for (let count = 0; count < 150; count += 1) {
      const answer = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie } }));
      statuses.add(answer.status);
    }
    expect([...statuses]).toEqual([200]);
  });

  it("keeps no visitor address nor browser in the session", async () => {
    const database = { user: [], session: [] as Record<string, unknown>[], account: [], verification: [] };
    const mails: Mail[] = [];
    const auth = createAuth(SETTINGS, { database: memoryAdapter(database), guard: async () => ({ ok: true }), deposit: async (mail) => void mails.push(mail), erase: async () => true });
    await auth.handler(post("/sign-up/email", { email: "ada@example.com", password: PASSWORD, name: "" }));
    const link = mails[0]?.link ?? "";
    await auth.handler(new Request(link, { headers: { "x-mcplain-limiter-ip": "203.0.113.7", "User-Agent": "Browser" } }));
    expect(database.session).toHaveLength(1);
    expect(database.session[0]).toMatchObject({ ipAddress: null, userAgent: null });
  });
});

describe("the outbox and the limiter address", () => {
  it("reads the language of the mail from the site, English by default", () => {
    expect(mailLanguage(new Request(ORIGIN, { headers: { "x-mcplain-lang": "fr" } }))).toBe("fr");
    expect(mailLanguage(new Request(ORIGIN, { headers: { "x-mcplain-lang": "de" } }))).toBe("en");
    expect(mailLanguage(undefined)).toBe("en");
  });

  it("writes one row in public.mail_outbox, its only right outside the auth schema", async () => {
    const query = vi.fn(async () => ({ rows: [] }));
    await outboxDeposit({ query } as never)({ kind: "verify_email", lang: "fr", recipient: "ada@example.com", link: `${ORIGIN}/x` });
    const [sql, values] = query.mock.calls[0] as unknown as [string, unknown[]];
    expect(sql).toMatch(/^INSERT INTO public\.mail_outbox /);
    expect(values.slice(1)).toEqual(["verify_email", "fr", "ada@example.com", `${ORIGIN}/x`]);
  });

  it("gives the limiter the address our relay appended, never one the browser wrote", () => {
    expect(limiterAddress({ "x-forwarded-for": "6.6.6.6, 203.0.113.7" }, 1)).toBe("203.0.113.7");
    expect(limiterAddress({ "x-forwarded-for": "6.6.6.6, 203.0.113.7, 10.0.0.2" }, 2)).toBe("203.0.113.7");
    expect(limiterAddress({}, 1)).toBeNull();
    const headers: Record<string, string> = { "x-forwarded-for": "203.0.113.7", [LIMITER_IP_HEADER]: "6.6.6.6" };
    setLimiterAddress(headers, 1);
    expect(headers[LIMITER_IP_HEADER]).toBe("203.0.113.7");
    const empty: Record<string, string> = { [LIMITER_IP_HEADER]: "6.6.6.6" };
    setLimiterAddress(empty, 1);
    expect(empty[LIMITER_IP_HEADER]).toBeUndefined();
  });
});
