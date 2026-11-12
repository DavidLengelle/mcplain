import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "@/components/account/forgot-password-form";
import { SignInForm } from "@/components/account/sign-in-form";
import { SignUpForm } from "@/components/account/sign-up-form";
import { authHeaders, passwordFits } from "@/lib/auth-client";
import { authErrorKey } from "@/lib/auth-errors";

import { renderWithIntl } from "./intl";

const push = vi.fn();
const signUp = vi.fn();
const signIn = vi.fn();
const requestPasswordReset = vi.fn();
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
    signUp: { email: (...args: unknown[]) => signUp(...args) },
    signIn: { email: (...args: unknown[]) => signIn(...args) },
    requestPasswordReset: (...args: unknown[]) => requestPasswordReset(...args),
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

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

beforeEach(() => {
  solve.mockResolvedValue("PAYLOAD");
});

describe("the error messages of the accounts", () => {
  it("never tell whether an account exists", () => {
    expect(authErrorKey({ code: "INVALID_EMAIL_OR_PASSWORD", status: 401 })).toBe("invalidCredentials");
    expect(authErrorKey({ code: "USER_NOT_FOUND", status: 404 })).toBe("invalidCredentials");
    expect(authErrorKey({ code: "SIGNUP_LIMIT", status: 429 })).toBe("signupLimit");
    expect(authErrorKey({ code: "ALTCHA_INVALID", status: 403 })).toBe("altcha");
    expect(authErrorKey({ status: 429 })).toBe("tooMany");
    expect(authErrorKey({ code: "SOMETHING_NEW", status: 500 })).toBe("unavailable");
    expect(passwordFits("123456789")).toBe(false);
    expect(passwordFits("1234567890")).toBe(true);
    expect(passwordFits("x".repeat(129))).toBe(false);
    expect(authHeaders("fr", "P")).toEqual({ "x-mcplain-lang": "fr", "x-altcha": "P" });
  });
});

describe("the account forms", () => {
  it("sign in: sends the ALTCHA payload and says email or password incorrect", async () => {
    signIn.mockResolvedValue({ data: null, error: { code: "INVALID_EMAIL_OR_PASSWORD", status: 401 } });
    renderWithIntl(<SignInForm />, "fr");
    fill("Adresse e-mail", "ada@example.com");
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "SE CONNECTER" }));
    expect(await screen.findByText("E-mail ou mot de passe incorrect.")).toBeTruthy();
    const [body, options] = signIn.mock.calls[0] as [Record<string, string>, { headers: Record<string, string> }];
    expect(body).toMatchObject({ email: "ada@example.com", password: PASSWORD, callbackURL: "/fr/account" });
    expect(options.headers).toEqual({ "x-mcplain-lang": "fr", "x-altcha": "PAYLOAD" });
    expect(push).not.toHaveBeenCalled();
  });

  it("sign in: the password goes back to hidden after a refused submit", async () => {
    signIn.mockResolvedValue({ data: null, error: { code: "INVALID_EMAIL_OR_PASSWORD", status: 401 } });
    renderWithIntl(<SignInForm />, "en");
    fill("Email address", "ada@example.com");
    fill("Password", PASSWORD);
    const toggle = screen.getByLabelText("Show password") as HTMLInputElement;
    fireEvent.click(toggle);
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "SIGN IN" }));
    expect(await screen.findByText("Email or password incorrect.")).toBeTruthy();
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(toggle.checked).toBe(false);
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe(PASSWORD);
  });

  it("sign in: goes to the account page once signed in", async () => {
    signIn.mockResolvedValue({ data: { user: {} }, error: null });
    renderWithIntl(<SignInForm />, "en");
    fill("Email address", "ada@example.com");
    fill("Password", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "SIGN IN" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
  });

  it("sign up: the limit of the network gets its own message, in both languages", async () => {
    signUp.mockResolvedValue({ data: null, error: { code: "SIGNUP_LIMIT", status: 429 } });
    renderWithIntl(<SignUpForm />, "fr");
    fill("Adresse e-mail", "ada@example.com");
    fill("Mot de passe", PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "CRÉER MON COMPTE" }));
    expect(
      await screen.findByText(
        "Trop de comptes ont été créés depuis ce réseau aujourd'hui. Réessaie demain, ou depuis un autre réseau (la 4G de ton téléphone, par exemple).",
      ),
    ).toBeTruthy();
  });

  it("sign up: refuses a short password before asking anything", async () => {
    renderWithIntl(<SignUpForm />, "en");
    fill("Email address", "ada@example.com");
    fill("Password", "short");
    fireEvent.click(screen.getByRole("button", { name: "CREATE MY ACCOUNT" }));
    expect(await screen.findByText("The password must have 10 to 128 characters.")).toBeTruthy();
    expect(signUp).not.toHaveBeenCalled();
    expect(solve).not.toHaveBeenCalled();
  });

  it("sign up: shows the address typed by the visitor as raw text", async () => {
    signUp.mockResolvedValue({ data: { user: {} }, error: null });
    const typed = "<b>ada</b>@example.com";
    renderWithIntl(<SignUpForm />, "en");
    fill("Email address", typed);
    fill("Password", PASSWORD);
    const form = screen.getByRole("button", { name: "CREATE MY ACCOUNT" }).closest("form");
    if (form === null) {
      throw new Error("the form is missing");
    }
    fireEvent.submit(form);
    expect(await screen.findByTestId("sign-up-done")).toBeTruthy();
    expect(screen.getByText(typed)).toBeTruthy();
    expect(document.querySelector("b")).toBeNull();
  });

  it("forgot password: always says an email may have been sent", async () => {
    requestPasswordReset.mockResolvedValue({ data: null, error: { code: "USER_NOT_FOUND", status: 404 } });
    renderWithIntl(<ForgotPasswordForm />, "fr");
    fill("Adresse e-mail", "nobody@example.com");
    fireEvent.click(screen.getByRole("button", { name: "ENVOYER LE LIEN" }));
    expect(await screen.findByText("Si un compte existe pour cette adresse, un e-mail est parti. Le lien marche pendant une heure.")).toBeTruthy();
  });

  it("forgot password: a failed ALTCHA is said plainly", async () => {
    solve.mockResolvedValue(null);
    renderWithIntl(<ForgotPasswordForm />, "en");
    fill("Email address", "ada@example.com");
    fireEvent.click(screen.getByRole("button", { name: "SEND THE LINK" }));
    expect(await screen.findByText("The automatic check failed. Try again.")).toBeTruthy();
    expect(requestPasswordReset).not.toHaveBeenCalled();
  });
});
