"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { getPathname, Link } from "@/i18n/navigation";
import { authClient, authHeaders } from "@/lib/auth-client";

import { AltchaField, type AltchaHandle } from "./altcha-field";
import { AccountCard, BUTTON_CLASS, Field, FormMessage, LINK_CLASS } from "./form-parts";
import { useAuthAction } from "./use-auth-action";

const GUARD_CODES = new Set(["ALTCHA_INVALID", "GUARD_UNAVAILABLE"]);

export function ForgotPasswordForm() {
  const t = useTranslations("account");
  const locale = useLocale();
  const altcha = useRef<AltchaHandle>(null);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const done = await run(async () => {
      const payload = (await altcha.current?.solve()) ?? null;
      if (payload === null) {
        setError("altcha");
        return null;
      }
      const redirectTo = getPathname({ href: "/account/new-password", locale });
      const outcome = await authClient.requestPasswordReset({ email: email.trim(), redirectTo }, { headers: authHeaders(locale, payload) });
      if (GUARD_CODES.has(outcome.error?.code ?? "") || outcome.error?.status === 429) {
        return outcome;
      }
      return { error: null };
    });
    if (done) {
      setSent(true);
    }
  }

  return (
    <AccountCard title={t("forgot.title")}>
      {sent && (
        <p data-testid="forgot-done" className="font-semibold text-ink">
          {t("forgot.done")}
        </p>
      )}
      {!sent && (
        <>
          <p>{t("forgot.intro")}</p>
          <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="forgot-error">
            <Field id="forgot-email" label={t("common.email")} type="email" value={email} onChange={setEmail} autoComplete="email" />
            <AltchaField ref={altcha} />
            <button type="submit" disabled={pending} className={BUTTON_CLASS}>
              {pending && t("common.busy")}
              {!pending && t("forgot.submit")}
            </button>
            <FormMessage id="forgot-error" tone="error">
              {error !== null && t(`errors.${error}`)}
            </FormMessage>
          </form>
        </>
      )}
      <p>
        <Link href="/account/sign-in" className={LINK_CLASS}>
          {t("forgot.backToSignIn")}
        </Link>
      </p>
    </AccountCard>
  );
}
