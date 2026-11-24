import { memoryAdapter } from "better-auth/adapters/memory";
import { describe, expect, it } from "vitest";

import { createAuth } from "../src/auth.ts";
import { LIMITER_IP_HEADER } from "../src/client-ip.ts";
import { banReason, internalRoutes } from "../src/internal.ts";
import type { Mail } from "../src/outbox.ts";
import { sessionRefusal, TWO_FACTOR_SESSION_PATHS } from "../src/session-gate.ts";
import type { Settings } from "../src/settings.ts";

const ORIGIN = "http://localhost:3010";
const PASSWORD = "a long enough password";
const REASON = "Spam ‮ <b>bold</b>";
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

let visitor = 0;

function post(path: string, body: unknown, cookie: string = ""): Request {
  visitor += 1;
  const headers: Record<string, string> = { "Content-Type": "application/json", Origin: ORIGIN, "x-altcha": "PAYLOAD", [LIMITER_IP_HEADER]: `192.0.2.${visitor % 250}` };
  if (cookie !== "") {
    headers.Cookie = cookie;
  }
  return new Request(`${ORIGIN}/api/auth${path}`, { method: "POST", headers, body: JSON.stringify(body) });
}

function sessionOf(response: Response): string {
  for (const item of response.headers.getSetCookie()) {
    const pair = item.split(";")[0] ?? "";
    if (pair.startsWith("mcplain.session_token=") && pair !== "mcplain.session_token=") {
      return pair;
    }
  }
  return "";
}

async function setup() {
  const tables = { user: [] as Row[], session: [] as Row[], account: [] as Row[], verification: [] as Row[], twoFactor: [] as Row[] };
  const mails: Mail[] = [];
  const auth = createAuth(SETTINGS, { database: memoryAdapter(tables), guard: async () => ({ ok: true }), deposit: async (mail) => void mails.push(mail), erase: async () => true });
  const routes = internalRoutes(auth);
  const signUp = async (email: string): Promise<{ id: string; cookie: string }> => {
    await auth.handler(post("/sign-up/email", { email, password: PASSWORD, name: "" }));
    const link = mails.filter((mail) => mail.recipient === email).at(-1)?.link ?? "";
    const cookie = sessionOf(await auth.handler(new Request(link, { headers: { Origin: ORIGIN } })));
    const row = tables.user.find((item) => item.email === email);
    return { id: String(row?.id), cookie };
  };
  const call = (method: string, path: string, body: unknown = {}, search: string = "") =>
    routes({ method, path, search: new URLSearchParams(search), cookie: undefined, body: JSON.stringify(body) });
  const session = (cookie: string) => routes({ method: "GET", path: "/internal/session", search: new URLSearchParams(), cookie, body: "" });
  return { auth, tables, signUp, call, session };
}

describe("bans, kept by the counter", () => {
  it("finds an account by its exact email only, with its ban state", async () => {
    const { signUp, call } = await setup();
    const { id } = await signUp("eve@example.com");
    const found = await call("GET", "/internal/accounts", {}, "email=Eve%40example.com");
    expect(found.status).toBe(200);
    expect(found.body).toMatchObject({ account: { id, email: "eve@example.com", role: "user", email_verified: true, two_factor: false, banned_at: null, ban_reason: null } });
    expect((await call("GET", "/internal/accounts", {}, "email=eve")).status).toBe(400);
    expect((await call("GET", "/internal/accounts", {}, "email=ev%40example.com")).status).toBe(404);
    expect((await call("GET", "/internal/accounts", {}, "")).status).toBe(400);
  });

  it("kills the sessions at once, refuses any new one with a neutral code, and the reason never leaves the counter", async () => {
    const { auth, tables, signUp, call, session } = await setup();
    const { id, cookie } = await signUp("eve@example.com");
    expect(((await session(cookie)).body as { user: Row }).user.banned).toBe(false);
    const banned = await call("POST", "/internal/accounts/ban", { user_id: id, reason: `  ${REASON}  ` });
    expect(banned).toEqual({ status: 200, body: { ok: true } });
    expect(tables.session.filter((item) => item.userId === id)).toEqual([]);
    expect((await session(cookie)).body).toEqual({ user: null });
    const signIn = await auth.handler(post("/sign-in/email", { email: "eve@example.com", password: PASSWORD }));
    expect(signIn.status).toBe(403);
    const text = await signIn.text();
    expect(JSON.parse(text)).toMatchObject({ code: "ACCOUNT_BLOCKED", message: "Refused" });
    expect(text).not.toContain("Spam");
    expect(sessionOf(signIn)).toBe("");
    expect(tables.session.filter((item) => item.userId === id)).toEqual([]);
    const wrong = await auth.handler(post("/sign-in/email", { email: "eve@example.com", password: "a wrong password" }));
    expect(wrong.status).toBe(401);
    const found = await call("GET", "/internal/accounts", {}, "email=eve%40example.com");
    expect((found.body as { account: Row }).account.ban_reason).toBe(REASON);
    expect((found.body as { account: Row }).account.banned_at).not.toBeNull();
  });

  it("refuses to ban an admin, and lifts a ban so that the account signs in again", async () => {
    const { auth, tables, signUp, call } = await setup();
    const boss = await signUp("boss@example.com");
    const row = tables.user.find((item) => item.id === boss.id);
    if (row !== undefined) {
      row.role = "admin";
    }
    expect(await call("POST", "/internal/accounts/ban", { user_id: boss.id })).toEqual({ status: 409, body: { error: "is_admin" } });
    expect(tables.session.filter((item) => item.userId === boss.id)).toHaveLength(1);
    const eve = await signUp("eve@example.com");
    expect((await call("POST", "/internal/accounts/ban", { user_id: eve.id, reason: null })).status).toBe(200);
    expect((await call("POST", "/internal/accounts/unban", { user_id: eve.id })).status).toBe(200);
    const signIn = await auth.handler(post("/sign-in/email", { email: "eve@example.com", password: PASSWORD }));
    expect(signIn.status).toBe(200);
    expect(sessionOf(signIn)).not.toBe("");
    const found = await call("GET", "/internal/accounts", {}, "email=eve%40example.com");
    expect(found.body).toMatchObject({ account: { banned_at: null, ban_reason: null } });
  });

  it("checks the request: unknown account, missing id, reason over 200 characters", async () => {
    const { signUp, call } = await setup();
    const { id } = await signUp("eve@example.com");
    expect((await call("POST", "/internal/accounts/ban", { user_id: "nobody" })).status).toBe(404);
    expect((await call("POST", "/internal/accounts/unban", { user_id: "nobody" })).status).toBe(404);
    expect((await call("POST", "/internal/accounts/ban", {})).status).toBe(400);
    expect((await call("POST", "/internal/accounts/ban", { user_id: id, reason: "x".repeat(201) })).status).toBe(400);
    expect((await call("POST", "/internal/accounts/ban", { user_id: id, reason: 12 })).status).toBe(400);
    expect((await call("GET", "/internal/accounts/ban", { user_id: id })).status).toBe(404);
    expect(banReason("x".repeat(200))).toHaveLength(200);
    expect(banReason("   ")).toBeNull();
  });

  it("refuses a session to a banned account on every route, the exceptions of the second factor included", () => {
    const banned = { id: "e", twoFactorEnabled: true, bannedAt: new Date() };
    for (const path of [...TWO_FACTOR_SESSION_PATHS, "/verify-email", undefined]) {
      expect(sessionRefusal(banned, path)).toBe("ACCOUNT_BLOCKED");
    }
    expect(sessionRefusal({ id: "e", twoFactorEnabled: false, bannedAt: "2026-11-24T00:00:00Z" }, "/sign-in/email")).toBe("ACCOUNT_BLOCKED");
  });

  it("never sends the ban fields to the browser", async () => {
    const { auth, signUp } = await setup();
    const { cookie } = await signUp("eve@example.com");
    const answer = await auth.handler(new Request(`${ORIGIN}/api/auth/get-session`, { headers: { Cookie: cookie, [LIMITER_IP_HEADER]: "192.0.2.251" } }));
    const user = ((await answer.json()) as { user: Row }).user;
    expect(user).not.toHaveProperty("bannedAt");
    expect(user).not.toHaveProperty("banReason");
  });
});
