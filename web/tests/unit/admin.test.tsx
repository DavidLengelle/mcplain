import { fireEvent, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SecuritySection } from "@/components/account/security-section";
import { SignInForm } from "@/components/account/sign-in-form";
import { AdminPanel } from "@/components/admin/admin-panel";
import { banAccount, findAccount, parseAccount, unbanAccount } from "@/lib/admin";
import { authErrorKey } from "@/lib/auth-errors";
import { asksSecondFactor, hasTwoFactor, isAdminRole, keyGroups, secretFromUri, typedBackupCode, typedCode } from "@/lib/two-factor";

import { renderWithIntl } from "./intl";

const push = vi.fn();
const signIn = vi.fn();
const verifyTotp = vi.fn();
const verifyBackupCode = vi.fn();
const enable = vi.fn();
const disable = vi.fn();
const generateBackupCodes = vi.fn();
const useSession = vi.fn();
const solve = vi.fn();

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push }),
  getPathname: ({ href, locale }: { href: string; locale: string }) => `/${locale}${href}`,
  Link: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/auth-client", async (original) => ({
  ...(await original<typeof import("@/lib/auth-client")>()),
  authClient: {
    signIn: { email: (...args: unknown[]) => signIn(...args) },
    useSession: () => useSession(),
    twoFactor: {
      verifyTotp: (...args: unknown[]) => verifyTotp(...args),
      verifyBackupCode: (...args: unknown[]) => verifyBackupCode(...args),
      enable: (...args: unknown[]) => enable(...args),
      disable: (...args: unknown[]) => disable(...args),
      generateBackupCodes: (...args: unknown[]) => generateBackupCodes(...args),
    },
  },
}));

vi.mock("@/components/account/altcha-field", async () => {
  const { useImperativeHandle } = await import("react");
  return {
    AltchaField: ({ ref }: { ref: React.Ref<{ solve: () => Promise<string | null> }> }) => {
      useImperativeHandle(ref, () => ({ solve: () => solve() }));
      return null;
    },
  };
});

const PASSWORD = "a long enough password";
const SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
const URI = `otpauth://totp/MCPlain:boss%40example.com?secret=${SECRET}&issuer=MCPlain&digits=6&period=30`;
const CODES = ["a1b2c-3d4e5", "f6g7h-8i9j0"];
const ADMIN = { id: "a1", email: "boss@example.com", role: "admin", twoFactorEnabled: true };

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  solve.mockResolvedValue("PAYLOAD");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the helpers of the second factor", () => {
  it("reads the key of the otpauth link, groups it by 4, and cleans a pasted code", () => {
    expect(secretFromUri(URI)).toBe(SECRET);
    expect(secretFromUri("https://example.com/?secret=ABC")).toBeNull();
    expect(secretFromUri("otpauth://totp/x?secret=not%20base32")).toBeNull();
    expect(secretFromUri("not a link")).toBeNull();
    expect(keyGroups("ABCDEFGHIJ")).toEqual(["ABCD", "EFGH", "IJ"]);
    expect(typedCode(" 123 456 ")).toBe("123456");
    expect(typedCode("12-34-5678")).toBe("123456");
    expect(typedBackupCode(" a1b2c-3d4e5 ")).toBe("a1b2c-3d4e5");
    expect(isAdminRole({ role: "admin" })).toBe(true);
    expect(isAdminRole({ role: "bench" })).toBe(false);
    expect(hasTwoFactor({ twoFactorEnabled: "true" })).toBe(false);
    expect(asksSecondFactor({ twoFactorRedirect: true })).toBe(true);
    expect(asksSecondFactor(null)).toBe(false);
  });

  it("maps the codes of the counter to plain messages", () => {
    expect(authErrorKey({ code: "ACCOUNT_BLOCKED", status: 403 })).toBe("accountBlocked");
    expect(authErrorKey({ code: "INVALID_CODE", status: 401 })).toBe("wrongCode");
    expect(authErrorKey({ code: "INVALID_BACKUP_CODE", status: 401 })).toBe("wrongCode");
    expect(authErrorKey({ code: "ACCOUNT_TEMPORARILY_LOCKED", status: 429 })).toBe("locked");
    expect(authErrorKey({ code: "TOO_MANY_ATTEMPTS_REQUEST_NEW_CODE", status: 400 })).toBe("codeExpired");
    expect(authErrorKey({ code: "TWO_FACTOR_REQUIRED", status: 403 })).toBe("signInAgain");
  });
});

describe("the sign-in with a second factor", () => {
  async function passwordStep() {
    signIn.mockResolvedValue({ data: { twoFactorRedirect: true, twoFactorMethods: ["totp"] }, error: null });
    renderWithIntl(<SignInForm />, "fr");
    fill("Adresse e-mail", "boss@example.com");
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "SE CONNECTER" }));
    return screen.findByTestId("two-factor-step");
  }

  it("asks the code after the password, with a numeric keyboard, a pasted code accepted, and never trustDevice", async () => {
    await passwordStep();
    expect(push).not.toHaveBeenCalled();
    const field = screen.getByLabelText("Code à 6 chiffres") as HTMLInputElement;
    expect(field.inputMode).toBe("numeric");
    expect(field.autocomplete).toBe("one-time-code");
    fireEvent.change(field, { target: { value: "123 456" } });
    expect(field.value).toBe("123456");
    verifyTotp.mockResolvedValue({ data: {}, error: null });
    fireEvent.click(screen.getByRole("button", { name: "VÉRIFIER" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
    expect(verifyTotp).toHaveBeenCalledWith({ code: "123456" });
  });

  it("says plainly a wrong code, a locked account and a blocked account", async () => {
    await passwordStep();
    verifyTotp.mockResolvedValue({ data: null, error: { code: "INVALID_CODE", status: 401 } });
    fill("Code à 6 chiffres", "000000");
    fireEvent.click(screen.getByRole("button", { name: "VÉRIFIER" }));
    expect(await screen.findByText(/Ce code n'est pas le bon/)).toBeTruthy();
    verifyTotp.mockResolvedValue({ data: null, error: { code: "ACCOUNT_TEMPORARILY_LOCKED", status: 429 } });
    fill("Code à 6 chiffres", "000000");
    fireEvent.click(screen.getByRole("button", { name: "VÉRIFIER" }));
    expect(await screen.findByText("Trop de codes faux. Le compte est verrouillé pendant 15 minutes.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Recommencer la connexion" })).toBeTruthy();
  });

  it("offers a backup code instead of the app", async () => {
    await passwordStep();
    fireEvent.click(screen.getByRole("button", { name: "Utiliser un code de secours" }));
    verifyBackupCode.mockResolvedValue({ data: {}, error: null });
    fill("Code de secours", " a1b2c-3d4e5 ");
    fireEvent.click(screen.getByRole("button", { name: "VÉRIFIER" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
    expect(verifyBackupCode).toHaveBeenCalledWith({ code: "a1b2c-3d4e5" });
  });

  it("says only that the account is blocked", async () => {
    signIn.mockResolvedValue({ data: null, error: { code: "ACCOUNT_BLOCKED", status: 403 } });
    renderWithIntl(<SignInForm />, "fr");
    fill("Adresse e-mail", "eve@example.com");
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "SE CONNECTER" }));
    expect(await screen.findByText("Ce compte est bloqué.")).toBeTruthy();
  });
});

describe("the security part of the account", () => {
  it("turns the second factor on: password, the key grouped by 4, a first code, then the backup codes once", async () => {
    enable.mockResolvedValue({ data: { totpURI: URI, backupCodes: CODES }, error: null });
    verifyTotp.mockResolvedValue({ data: {}, error: null });
    renderWithIntl(<SecuritySection user={{ ...ADMIN, twoFactorEnabled: false }} />, "fr");
    expect(screen.getByTestId("two-factor-off")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "ACTIVER LA DOUBLE AUTHENTIFICATION" }));
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "CONTINUER" }));
    const key = await screen.findByTestId("totp-key");
    expect(key.textContent).toBe(SECRET);
    expect(key.textContent).not.toMatch(/\s/);
    expect(Array.from(key.querySelectorAll("[data-key-group]"), (group) => group.textContent)).toEqual(keyGroups(SECRET));
    for (const group of key.querySelectorAll("[data-key-group]")) {
      expect(group.textContent?.length).toBeLessThanOrEqual(4);
    }
    expect(enable).toHaveBeenCalledWith({ password: PASSWORD });
    expect(screen.queryByText(CODES[0] ?? "")).toBeNull();
    fill("Code à 6 chiffres", "123456");
    fireEvent.click(screen.getByRole("button", { name: "CONFIRMER" }));
    const sheet = await screen.findByTestId("backup-codes");
    expect(sheet.hasAttribute("data-print-area")).toBe(true);
    expect(screen.getAllByTestId("backup-code").map((item) => item.textContent)).toEqual(CODES);
    expect(screen.queryByTestId("totp-key")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "J'AI RANGÉ MES CODES" }));
    expect(screen.queryByTestId("backup-codes")).toBeNull();
  });

  it("prints the codes in the light theme, then gives the chosen theme back", async () => {
    generateBackupCodes.mockResolvedValue({ data: { backupCodes: CODES }, error: null });
    const print = vi.fn(() => {
      expect(document.documentElement.classList.contains("th-light")).toBe(true);
      expect(document.documentElement.classList.contains("th-dark")).toBe(false);
      expect(document.documentElement.dataset.printing).toBe("codes");
    });
    vi.stubGlobal("print", print);
    document.documentElement.classList.add("th-dark");
    renderWithIntl(<SecuritySection user={ADMIN} />, "en");
    fireEvent.click(screen.getByRole("button", { name: "Make new backup codes" }));
    fill("Password", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "MAKE NEW CODES" }));
    await screen.findByTestId("backup-codes");
    fireEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement.classList.contains("th-dark")).toBe(true);
    expect(document.documentElement.classList.contains("th-light")).toBe(false);
    expect(document.documentElement.dataset.printing).toBeUndefined();
    document.documentElement.classList.remove("th-dark");
  });

  it("warns that turning it off removes the admin powers", async () => {
    disable.mockResolvedValue({ data: { status: true }, error: null });
    renderWithIntl(<SecuritySection user={ADMIN} />, "fr");
    fireEvent.click(screen.getByRole("button", { name: "Désactiver la double authentification" }));
    expect(screen.getByTestId("disable-warning").textContent).toContain("tu perds tes pouvoirs d'admin");
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "DÉSACTIVER" }));
    await waitFor(() => expect(disable).toHaveBeenCalledWith({ password: PASSWORD }));
  });

  it("keeps the print rules in the one stylesheet, without any color", () => {
    const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf-8");
    const print = css.slice(css.indexOf("@media print"));
    expect(print).toContain('html[data-printing="codes"] [data-print-area]');
    expect(print).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgb|hsl/);
  });
});

describe("the admin desk", () => {
  it("shows only the way to the security part to an admin without second factor", () => {
    useSession.mockReturnValue({ isPending: false, data: { user: { ...ADMIN, twoFactorEnabled: false } } });
    renderWithIntl(<AdminPanel />, "fr");
    expect(screen.getByTestId("admin-needs-two-factor").textContent).toBe("Active la double authentification");
    expect(screen.getByRole("link", { name: "Aller à la section Sécurité de mon compte" }).getAttribute("href")).toBe("/account#security");
    expect(screen.queryByText("Comptes")).toBeNull();
  });

  it("is closed to a normal account", () => {
    useSession.mockReturnValue({ isPending: false, data: { user: { id: "u1", role: "user", twoFactorEnabled: true } } });
    renderWithIntl(<AdminPanel />, "en");
    expect(screen.getByTestId("admin-not-admin")).toBeTruthy();
  });

  it("finds an account, shows its reason as raw text, blocks and unblocks it", async () => {
    useSession.mockReturnValue({ isPending: false, data: { user: ADMIN } });
    const reason = "spam \u202E<b>x</b>";
    const states = [
      { id: "e1", email: "eve@example.com", role: "user", banned_at: null, ban_reason: null, created_at: "2026-11-01T10:00:00Z" },
      { id: "e1", email: "eve@example.com", role: "user", banned_at: "2026-11-24T10:00:00Z", ban_reason: reason, created_at: "2026-11-01T10:00:00Z" },
    ];
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (url.startsWith("/api/admin/accounts?")) {
          const banned = calls.some((call) => call.url.endsWith("/ban"));
          return answer(200, { account: states[Number(banned)] });
        }
        return answer(200, { ok: true });
      }),
    );
    renderWithIntl(<AdminPanel />, "fr");
    const dashboard = screen.getByTestId("admin-dashboard");
    const accounts = screen.getByRole("heading", { name: "Comptes" });
    expect(dashboard.compareDocumentPosition(accounts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fill("Adresse e-mail exacte", "eve@example.com");
    fireEvent.click(screen.getByRole("button", { name: "CHERCHER" }));
    expect((await screen.findByTestId("admin-account-state")).textContent).toBe("Actif");
    fill("Motif du blocage (facultatif, vu par l'admin seulement)", reason);
    fireEvent.click(screen.getByRole("button", { name: "BLOQUER CE COMPTE" }));
    const shown = await screen.findByTestId("admin-account-reason");
    expect(shown.querySelector("b")).toBeNull();
    expect(shown.textContent).not.toContain("\u202E");
    const ban = calls.find((call) => call.url.endsWith("/ban"));
    expect(ban?.url).toBe("/api/admin/accounts/e1/ban");
    expect(JSON.parse(String(ban?.init?.body))).toEqual({ reason });
    fireEvent.click(screen.getByRole("button", { name: "Débloquer ce compte" }));
    await waitFor(() => expect(calls.some((call) => call.url === "/api/admin/accounts/e1/unban")).toBe(true));
  });

  it("never offers to block an admin nor oneself", async () => {
    useSession.mockReturnValue({ isPending: false, data: { user: ADMIN } });
    vi.stubGlobal("fetch", vi.fn(async () => answer(200, { account: { id: "a1", email: "boss@example.com", role: "admin", banned_at: null } })));
    renderWithIntl(<AdminPanel />, "en");
    fill("Exact email address", "boss@example.com");
    fireEvent.click(screen.getByRole("button", { name: "FIND" }));
    expect(await screen.findByText("An admin account cannot be blocked.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "BLOCK THIS ACCOUNT" })).toBeNull();
  });
});

describe("the admin client", () => {
  it("reads the answers of the API and keeps no unknown field", async () => {
    expect(parseAccount({ account: { id: "e1", email: "e@example.com", secret: "x" } })).toEqual({
      id: "e1",
      email: "e@example.com",
      role: "user",
      emailVerified: false,
      twoFactor: false,
      createdAt: null,
      bannedAt: null,
      banReason: null,
    });
    expect(parseAccount({ account: { email: "e@example.com" } })).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => answer(404, { error: { code: "api.account_not_found" } })));
    expect(await findAccount("x@example.com")).toEqual({ kind: "missing" });
    vi.stubGlobal("fetch", vi.fn(async () => answer(403, { error: { code: "api.cannot_ban_self" } })));
    expect(await banAccount("a1", "  ")).toBe("self");
    vi.stubGlobal("fetch", vi.fn(async () => answer(403, { error: { code: "api.origin_refused" } })));
    expect(await unbanAccount("e1")).toBe("refused");
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("down");
    }));
    expect(await findAccount("x@example.com")).toEqual({ kind: "failed" });
  });
});
