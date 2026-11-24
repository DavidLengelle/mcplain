"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { authClient } from "@/lib/auth-client";
import { CODE_DIGITS } from "@/lib/two-factor";

import { CodeField } from "./code-field";
import { BUTTON_CLASS, FormMessage, LINK_CLASS } from "./form-parts";
import { useAuthAction } from "./use-auth-action";

export function TwoFactorStep({ onDone, onRestart }: { onDone: () => void; onRestart: () => void }) {
  const t = useTranslations("account");
  const [kind, setKind] = useState<"totp" | "backup">("totp");
  const [code, setCode] = useState("");
  const { pending, error, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const done = await run(() => {
      if (kind === "totp") {
        return authClient.twoFactor.verifyTotp({ code });
      }
      return authClient.twoFactor.verifyBackupCode({ code });
    });
    setCode("");
    if (done) {
      onDone();
    }
  }

  function switchTo(next: "totp" | "backup") {
    setKind(next);
    setCode("");
  }

  let ready = code !== "";
  if (kind === "totp") {
    ready = code.length === CODE_DIGITS;
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="code-error" data-testid="two-factor-step">
      {kind === "totp" && (
        <>
          <p>{t("twoFactor.intro")}</p>
          <CodeField id="two-factor-code" kind="totp" label={t("twoFactor.codeLabel")} help={t("twoFactor.codeHelp")} value={code} onChange={setCode} />
        </>
      )}
      {kind === "backup" && (
        <>
          <p>{t("twoFactor.backupIntro")}</p>
          <CodeField id="backup-code" kind="backup" label={t("twoFactor.backupLabel")} help={t("twoFactor.backupHelp")} value={code} onChange={setCode} />
        </>
      )}
      <button type="submit" disabled={pending || !ready} className={BUTTON_CLASS}>
        {pending && t("common.busy")}
        {!pending && t("twoFactor.submit")}
      </button>
      <FormMessage id="code-error" tone="error">
        {error !== null && t(`errors.${error}`)}
      </FormMessage>
      {kind === "totp" && (
        <button type="button" onClick={() => switchTo("backup")} className={`${LINK_CLASS} cursor-pointer self-start bg-transparent`}>
          {t("twoFactor.useBackup")}
        </button>
      )}
      {kind === "backup" && (
        <button type="button" onClick={() => switchTo("totp")} className={`${LINK_CLASS} cursor-pointer self-start bg-transparent`}>
          {t("twoFactor.useApp")}
        </button>
      )}
      {(error === "codeExpired" || error === "locked") && (
        <button type="button" onClick={onRestart} className={`${LINK_CLASS} cursor-pointer self-start bg-transparent`}>
          {t("twoFactor.restart")}
        </button>
      )}
    </form>
  );
}
