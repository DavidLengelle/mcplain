"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { getPathname, Link, useRouter } from "@/i18n/navigation";
import { authClient, authHeaders } from "@/lib/auth-client";

import { AltchaField, type AltchaHandle } from "./altcha-field";
import { AccountCard, BUTTON_CLASS, Field, FormMessage, LINK_CLASS } from "./form-parts";
import { useAuthAction } from "./use-auth-action";

export function SignInForm() {
  const t = useTranslations("account");
  const locale = useLocale();
  const router = useRouter();
  const altcha = useRef<AltchaHandle>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const done = await run(async () => {
      const payload = (await altcha.current?.solve()) ?? null;
      if (payload === null) {
        setError("altcha");
        return null;
      }
      const callbackURL = getPathname({ href: "/account", locale });
      return authClient.signIn.email({ email: email.trim(), password, callbackURL }, { headers: authHeaders(locale, payload) });
    });
    if (done) {
      setPassword("");
      router.push("/account");
    }
  }

  return (
    <AccountCard title={t("signIn.title")}>
      <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="sign-in-error">
        <Field id="sign-in-email" label={t("common.email")} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          id="sign-in-password"
          label={t("common.password")}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
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
