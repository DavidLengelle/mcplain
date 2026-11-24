"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { getPathname, Link, useRouter } from "@/i18n/navigation";
import { authClient, authHeaders } from "@/lib/auth-client";
import { asksSecondFactor } from "@/lib/two-factor";

import { AltchaField, type AltchaHandle } from "./altcha-field";
import { AccountCard, BUTTON_CLASS, EmailField, FormMessage, LINK_CLASS } from "./form-parts";
import { PasswordField } from "./password-field";
import { TwoFactorStep } from "./two-factor-step";
import { useAuthAction } from "./use-auth-action";

export function SignInForm() {
  const t = useTranslations("account");
  const locale = useLocale();
  const router = useRouter();
  const altcha = useRef<AltchaHandle>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordReset, setPasswordReset] = useState(0);
  const [secondStep, setSecondStep] = useState(false);
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordReset((count) => count + 1);
    let second = false;
    const done = await run(async () => {
      const payload = (await altcha.current?.solve()) ?? null;
      if (payload === null) {
        setError("altcha");
        return null;
      }
      const callbackURL = getPathname({ href: "/account", locale });
      const outcome = await authClient.signIn.email({ email: email.trim(), password, callbackURL }, { headers: authHeaders(locale, payload) });
      second = !outcome.error && asksSecondFactor(outcome.data);
      return outcome;
    });
    if (done) {
      setPassword("");
    }
    if (done && second) {
      setSecondStep(true);
      return;
    }
    if (done) {
      router.push("/account");
    }
  }

  if (secondStep) {
    return (
      <AccountCard title={t("twoFactor.title")}>
        <TwoFactorStep onDone={() => router.push("/account")} onRestart={() => setSecondStep(false)} />
      </AccountCard>
    );
  }

  return (
    <AccountCard title={t("signIn.title")}>
      <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="sign-in-error">
        <EmailField id="sign-in-email" label={t("common.email")} value={email} onChange={setEmail} />
        <PasswordField
          id="sign-in-password"
          label={t("common.password")}
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          resetCount={passwordReset}
        />
        <AltchaField ref={altcha} />
        <button type="submit" disabled={pending} className={BUTTON_CLASS}>
          {pending && t("common.busy")}
          {!pending && t("signIn.submit")}
        </button>
        <FormMessage id="sign-in-error" tone="error">
          {error !== null && t(`errors.${error}`)}
        </FormMessage>
      </form>
      <p>
        <Link href="/account/forgot-password" className={LINK_CLASS}>
          {t("signIn.forgot")}
        </Link>
      </p>
      <p>
        {t("signIn.noAccount")}{" "}
        <Link href="/account/sign-up" className={LINK_CLASS}>
          {t("signIn.signUpLink")}
        </Link>
      </p>
    </AccountCard>
  );
}
