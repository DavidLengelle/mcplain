"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { RawText } from "@/components/raw-text";
import { getPathname, Link } from "@/i18n/navigation";
import { authClient, authHeaders, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, passwordFits } from "@/lib/auth-client";

import { AltchaField, type AltchaHandle } from "./altcha-field";
import { AccountCard, BUTTON_CLASS, EmailField, FormMessage, LINK_CLASS } from "./form-parts";
import { PasswordField } from "./password-field";
import { useAuthAction } from "./use-auth-action";

export function SignUpForm() {
  const t = useTranslations("account");
  const locale = useLocale();
  const altcha = useRef<AltchaHandle>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordReset, setPasswordReset] = useState(0);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordReset((count) => count + 1);
    if (!passwordFits(password)) {
      setError("passwordLength");
      return;
    }
    const address = email.trim();
    const done = await run(async () => {
      const payload = (await altcha.current?.solve()) ?? null;
      if (payload === null) {
        setError("altcha");
        return null;
      }
      const callbackURL = getPathname({ href: "/account/verified", locale });
      return authClient.signUp.email(
        { email: address, password, name: "", callbackURL },
        { headers: authHeaders(locale, payload) },
      );
    });
    if (done) {
      setSentTo(address);
      setPassword("");
    }
  }

  if (sentTo !== null) {
    return (
      <AccountCard title={t("signUp.title")}>
        <p data-testid="sign-up-done">{t("signUp.done")}</p>
        <p className="font-mono text-ink">
          <RawText value={sentTo} />
        </p>
        <p>{t("signUp.doneNext")}</p>
      </AccountCard>
    );
  }

  return (
    <AccountCard title={t("signUp.title")}>
      <p>{t("signUp.intro")}</p>
      <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="sign-up-error">
        <EmailField id="sign-up-email" label={t("common.email")} value={email} onChange={setEmail} />
        <PasswordField
          id="sign-up-password"
          label={t("common.password")}
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          help={t("common.passwordHelp")}
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          resetCount={passwordReset}
        />
        <AltchaField ref={altcha} />
        <button type="submit" disabled={pending} className={BUTTON_CLASS}>
          {pending && t("common.busy")}
          {!pending && t("signUp.submit")}
        </button>
        <FormMessage id="sign-up-error" tone="error">
          {error !== null && t(`errors.${error}`)}
        </FormMessage>
      </form>
      <p>
        {t("signUp.haveAccount")}{" "}
        <Link href="/account/sign-in" className={LINK_CLASS}>
          {t("signUp.signInLink")}
        </Link>
      </p>
    </AccountCard>
  );
}
