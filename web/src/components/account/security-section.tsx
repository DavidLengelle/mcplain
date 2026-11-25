"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent, type ReactNode } from "react";

import { RawText } from "@/components/raw-text";
import { authClient } from "@/lib/auth-client";
import { CODE_DIGITS, groupedKey, hasTwoFactor, secretFromUri } from "@/lib/two-factor";

import { BackupCodes } from "./backup-codes";
import { CodeField } from "./code-field";
import { BUTTON_CLASS, FormMessage, SECONDARY_BUTTON_CLASS } from "./form-parts";
import { PasswordField } from "./password-field";
import { useAuthAction } from "./use-auth-action";

type Step =
  | { kind: "idle" }
  | { kind: "confirm"; action: "enable" | "regenerate" | "disable" }
  | { kind: "key"; secret: string; codes: string[] }
  | { kind: "codes"; codes: string[] };

type Enabled = { totpURI?: unknown; backupCodes?: unknown };

function codesOf(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function Box({ children }: { children: ReactNode }) {
  return <div className="mt-2 flex flex-col gap-4 rounded-[14px] bg-panel2 p-5">{children}</div>;
}

function PasswordStep({
  action,
  onEnabled,
  onCodes,
  onDisabled,
  onCancel,
}: {
  action: "enable" | "regenerate" | "disable";
  onEnabled: (secret: string, codes: string[]) => void;
  onCodes: (codes: string[]) => void;
  onDisabled: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("account");
  const [password, setPassword] = useState("");
  const [passwordReset, setPasswordReset] = useState(0);
  const { pending, error, setError, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordReset((count) => count + 1);
    let enabled: Enabled | null = null;
    let codes: string[] = [];
    const done = await run(async () => {
      if (action === "enable") {
        const outcome = await authClient.twoFactor.enable({ password });
        enabled = (outcome.data ?? null) as Enabled | null;
        return outcome;
      }
      if (action === "regenerate") {
        const outcome = await authClient.twoFactor.generateBackupCodes({ password });
        codes = codesOf(outcome.data?.backupCodes);
        return outcome;
      }
      return authClient.twoFactor.disable({ password });
    });
    setPassword("");
    if (!done) {
      return;
    }
    if (action === "disable") {
      onDisabled();
      return;
    }
    if (action === "regenerate") {
      onCodes(codes);
      return;
    }
    const answer: Enabled = enabled ?? {};
    const secret = secretFromUri(String(answer.totpURI ?? ""));
    if (secret === null) {
      setError("unavailable");
      return;
    }
    onEnabled(secret, codesOf(answer.backupCodes));
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="security-error">
      {action === "disable" && (
        <p data-testid="disable-warning" className="font-semibold text-red">
          {t("security.disableWarning")}
        </p>
      )}
      <p className="font-semibold text-ink">{t(`security.${action}Password`)}</p>
      <PasswordField
        id="security-password"
        label={t("common.password")}
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
        resetCount={passwordReset}
      />
      <div className="flex flex-wrap gap-3">
        <button type="submit" disabled={pending || password === ""} className={BUTTON_CLASS}>
          {pending && t("common.busy")}
          {!pending && t(`security.${action}Confirm`)}
        </button>
        <button type="button" onClick={onCancel} className={SECONDARY_BUTTON_CLASS}>
          {t("security.cancel")}
        </button>
      </div>
      <FormMessage id="security-error" tone="error">
        {error !== null && t(`errors.${error}`)}
      </FormMessage>
    </form>
  );
}

function KeyStep({ secret, onConfirmed, onCancel }: { secret: string; onConfirmed: () => void; onCancel: () => void }) {
  const t = useTranslations("account");
  const [code, setCode] = useState("");
  const { pending, error, run } = useAuthAction();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const done = await run(() => authClient.twoFactor.verifyTotp({ code }));
    setCode("");
    if (done) {
      onConfirmed();
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-describedby="key-error">
      <ol className="flex list-decimal flex-col gap-2 pl-6">
        <li>{t("security.stepOpen")}</li>
        <li>{t("security.stepName")}</li>
        <li>
          {t("security.stepKey")}
          <p data-testid="totp-key" className="mt-2 rounded-md bg-code-bg px-3 py-2 font-mono text-[18px] tracking-[0.08em] break-all text-ink select-all">
            <RawText value={groupedKey(secret)} />
          </p>
        </li>
        <li>{t("security.stepType")}</li>
        <li>{t("security.stepCode")}</li>
      </ol>
      <CodeField id="first-code" kind="totp" label={t("twoFactor.codeLabel")} help={t("twoFactor.codeHelp")} value={code} onChange={setCode} />
      <div className="flex flex-wrap gap-3">
        <button type="submit" disabled={pending || code.length !== CODE_DIGITS} className={BUTTON_CLASS}>
          {pending && t("common.busy")}
          {!pending && t("security.confirmKey")}
        </button>
        <button type="button" onClick={onCancel} className={SECONDARY_BUTTON_CLASS}>
          {t("security.cancel")}
        </button>
      </div>
      <FormMessage id="key-error" tone="error">
        {error !== null && t(`errors.${error}`)}
      </FormMessage>
    </form>
  );
}

export function SecuritySection({ user }: { user: unknown }) {
  const t = useTranslations("account.security");
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const enabled = hasTwoFactor(user);
  const idle = () => setStep({ kind: "idle" });

  let body: ReactNode = null;
  if (step.kind === "confirm") {
    body = (
      <PasswordStep
        action={step.action}
        onEnabled={(secret, codes) => setStep({ kind: "key", secret, codes })}
        onCodes={(codes) => setStep({ kind: "codes", codes })}
        onDisabled={idle}
        onCancel={idle}
      />
    );
  } else if (step.kind === "key") {
    const codes = step.codes;
    body = <KeyStep secret={step.secret} onConfirmed={() => setStep({ kind: "codes", codes })} onCancel={idle} />;
  } else if (step.kind === "codes") {
    body = <BackupCodes codes={step.codes} onDone={idle} />;
  } else if (enabled) {
    body = (
      <>
        <p data-testid="two-factor-on" className="font-semibold text-ink">
          {t("on")}
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={() => setStep({ kind: "confirm", action: "regenerate" })} className={SECONDARY_BUTTON_CLASS}>
            {t("regenerate")}
          </button>
          <button type="button" onClick={() => setStep({ kind: "confirm", action: "disable" })} className={SECONDARY_BUTTON_CLASS}>
            {t("disable")}
          </button>
        </div>
      </>
    );
  } else {
    body = (
      <>
        <p data-testid="two-factor-off" className="font-semibold text-ink">
          {t("off")}
        </p>
        <div>
          <button type="button" onClick={() => setStep({ kind: "confirm", action: "enable" })} className={BUTTON_CLASS}>
            {t("enable")}
          </button>
        </div>
      </>
    );
  }

  return (
    <section id="security" aria-labelledby="security-title" className="scroll-mt-4">
      <Box>
        <h2 id="security-title" className="font-condensed text-[26px] font-bold text-ink">
          {t("title")}
        </h2>
        <p>{t("intro")}</p>
        {body}
      </Box>
    </section>
  );
}
