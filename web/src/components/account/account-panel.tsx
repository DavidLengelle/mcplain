"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { RawText } from "@/components/raw-text";
import { Link, useRouter } from "@/i18n/navigation";
import { authClient } from "@/lib/auth-client";

import { AccountCard, BUTTON_CLASS, FormMessage, LINK_CLASS, SECONDARY_BUTTON_CLASS } from "./form-parts";
import { HistorySection } from "./history-section";
import { PasswordField } from "./password-field";
import { useAuthAction } from "./use-auth-action";

function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const t = useTranslations("account");
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [passwordReset, setPasswordReset] = useState(0);
  const { pending, error, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordReset((count) => count + 1);
    const done = await run(() => authClient.deleteUser({ password }));
    if (done) {
      setPassword("");
      onDeleted();
    }
  }

  return (
    <div className="mt-2 rounded-[14px] bg-panel2 p-5">
      <h2 className="font-condensed text-[26px] font-bold text-ink">{t("page.deleteTitle")}</h2>
      <p className="mt-2">{t("page.deleteIntro")}</p>
      {!open && (
        <button type="button" onClick={() => setOpen(true)} className={`${SECONDARY_BUTTON_CLASS} mt-4 font-semibold`}>
          {t("page.deleteStart")}
        </button>
      )}
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-4" aria-describedby="delete-error">
          <p className="font-semibold text-ink">{t("page.deleteConfirmIntro")}</p>
          <PasswordField
            id="delete-password"
            label={t("common.password")}
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            resetCount={passwordReset}
          />
          <div className="flex flex-wrap gap-3">
            <button type="submit" disabled={pending || password === ""} className={BUTTON_CLASS}>
              {pending && t("common.busy")}
              {!pending && t("page.deleteConfirm")}
            </button>
            <button type="button" onClick={() => setOpen(false)} className={SECONDARY_BUTTON_CLASS}>
              {t("page.deleteCancel")}
            </button>
          </div>
          <FormMessage id="delete-error" tone="error">
            {error !== null && t(`errors.${error}`)}
          </FormMessage>
        </form>
      )}
    </div>
  );
}

function LinkFailed({ shown }: { shown: boolean }) {
  const t = useTranslations("account");
  if (!shown) {
    return null;
  }
  return (
    <p data-testid="verified-error" className="font-semibold text-red">
      {t("verified.error")}
    </p>
  );
}

export function AccountPanel({ linkFailed = false }: { linkFailed?: boolean }) {
  const t = useTranslations("account");
  const router = useRouter();
  const session = authClient.useSession();
  const [deleted, setDeleted] = useState(false);
  const { pending, run } = useAuthAction();

  async function signOut() {
    const done = await run(() => authClient.signOut());
    if (done) {
      router.push("/");
    }
  }

  if (deleted) {
    return (
      <AccountCard title={t("page.title")}>
        <p data-testid="account-deleted" className="font-semibold text-ink">
          {t("page.deleted")}
        </p>
      </AccountCard>
    );
  }

  if (session.isPending) {
    return (
      <AccountCard title={t("page.title")}>
        <p>{t("common.loading")}</p>
      </AccountCard>
    );
  }

  const user = session.data?.user;
  if (!user) {
    return (
      <AccountCard title={t("page.title")}>
        <LinkFailed shown={linkFailed} />
        <p>{t("page.signedOut")}</p>
        <p>
          <Link href="/account/sign-in" className={LINK_CLASS}>
            {t("page.signInLink")}
          </Link>
        </p>
      </AccountCard>
    );
  }

  return (
    <AccountCard title={t("page.title")}>
      <LinkFailed shown={linkFailed} />
      <div>
        <p className="text-[15px] font-semibold text-muted">{t("page.emailLabel")}</p>
        <p data-testid="account-email" className="font-mono text-ink">
          <RawText value={user.email} />
        </p>
      </div>
      <div>
        <button type="button" onClick={signOut} disabled={pending} className={BUTTON_CLASS}>
          {t("menu.signOut")}
        </button>
      </div>
      <HistorySection />
      <DeleteAccount onDeleted={() => setDeleted(true)} />
    </AccountCard>
  );
}
