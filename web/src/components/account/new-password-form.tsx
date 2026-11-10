"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Link } from "@/i18n/navigation";
import { authClient, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, passwordFits } from "@/lib/auth-client";

import { AccountCard, BUTTON_CLASS, Field, FormMessage, LINK_CLASS } from "./form-parts";
import { useAuthAction } from "./use-auth-action";

export function NewPasswordForm({ token }: { token: string | null }) {
  const t = useTranslations("account");
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null) {
      return;
    }
    if (!passwordFits(password)) {
      setError("passwordLength");
      return;
    }
    const done = await run(() => authClient.resetPassword({ newPassword: password, token }));
    if (done) {
      setPassword("");
      setSaved(true);
    }
  }

  if (token === null) {
    return (
      <AccountCard title={t("newPassword.title")}>
        <p className="font-semibold text-red">{t("newPassword.invalidLink")}</p>
        <p>
          <Link href="/account/forgot-password" className={LINK_CLASS}>
            {t("newPassword.askAgain")}
          </Link>
        </p>
      </AccountCard>
    );
  }

  if (saved) {
    return (
      <AccountCard title={t("newPassword.title")}>
        <p data-testid="new-password-done" className="font-semibold text-ink">
          {t("newPassword.done")}
        </p>
        <p>
          <Link href="/account/sign-in" className={LINK_CLASS}>
            {t("newPassword.signInLink")}
          </Link>
        </p>
      </AccountCard>
    );
  }

  return (
    <AccountCard title={t("newPassword.title")}>
      <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="new-password-error">
        <Field
          id="new-password"
          label={t("newPassword.label")}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          help={t("common.passwordHelp")}
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
        />
        <button type="submit" disabled={pending} className={BUTTON_CLASS}>
          {pending && t("common.busy")}
          {!pending && t("newPassword.submit")}
        </button>
        <FormMessage id="new-password-error" tone="error">
          {error !== null && t(`errors.${error}`)}
        </FormMessage>
      </form>
      {error === "invalidToken" && (
        <p>
          <Link href="/account/forgot-password" className={LINK_CLASS}>
            {t("newPassword.askAgain")}
          </Link>
        </p>
      )}
    </AccountCard>
  );
}
