"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent, type ReactNode } from "react";

import { BUTTON_CLASS, EmailField, FormMessage, INPUT_CLASS, SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { useFormattedDate } from "@/components/report/identity-line";
import { BAN_REASON_MAX_CHARACTERS, banAccount, findAccount, unbanAccount, type AdminAccount, type ChangeOutcome } from "@/lib/admin";

type Found = { kind: "idle" } | { kind: "busy" } | { kind: "missing" } | { kind: "refused" } | { kind: "failed" } | { kind: "found"; account: AdminAccount };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <dt className="text-[15px] font-semibold text-muted sm:w-44">{label}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </div>
  );
}

function AccountView({ account, ownId, onChanged }: { account: AdminAccount; ownId: string; onChanged: (outcome: ChangeOutcome) => void }) {
  const t = useTranslations("admin.accounts");
  const formatDate = useFormattedDate();
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const banned = account.bannedAt !== null;
  const isAdmin = account.role === "admin";
  const isSelf = account.id === ownId;

  async function ban(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    const outcome = await banAccount(account.id, reason);
    setPending(false);
    if (outcome === "done") {
      setReason("");
    }
    onChanged(outcome);
  }

  async function unban() {
    setPending(true);
    const outcome = await unbanAccount(account.id);
    setPending(false);
    onChanged(outcome);
  }

  let state = t("stateActive");
  if (banned) {
    state = t("stateBlocked", { date: formatDate(account.bannedAt) ?? "" });
  }
  let twoFactor = t("no");
  if (account.twoFactor) {
    twoFactor = t("yes");
  }

  return (
    <div data-testid="admin-account" className="flex flex-col gap-4 rounded-[14px] bg-panel2 p-5">
      <dl className="flex flex-col gap-2">
        <Row label={t("email")}>
          <span className="font-mono break-all">
            <RawText value={account.email} />
          </span>
        </Row>
        <Row label={t("role")}>
          <span className="font-mono">
            <RawText value={account.role} />
          </span>
        </Row>
        <Row label={t("created")}>{formatDate(account.createdAt) ?? ""}</Row>
        <Row label={t("twoFactor")}>{twoFactor}</Row>
        <Row label={t("state")}>
          <span data-testid="admin-account-state" className="font-semibold">
            {state}
          </span>
        </Row>
        {banned && account.banReason !== null && (
          <Row label={t("reason")}>
            <span data-testid="admin-account-reason" className="break-words">
              <RawText value={account.banReason} />
            </span>
          </Row>
        )}
      </dl>
      {isAdmin && <p className="font-semibold text-ink">{t("adminNotBlockable")}</p>}
      {!isAdmin && isSelf && <p className="font-semibold text-ink">{t("selfNotBlockable")}</p>}
      {!isAdmin && !isSelf && !banned && (
        <form onSubmit={ban} className="flex flex-col gap-3">
          <label htmlFor="ban-reason" className="text-[15px] font-semibold text-ink">
            {t("reasonLabel")}
          </label>
          <textarea
            id="ban-reason"
            name="ban-reason"
            value={reason}
            maxLength={BAN_REASON_MAX_CHARACTERS}
            rows={2}
            aria-describedby="ban-reason-help"
            onChange={(event) => setReason(event.target.value)}
            className={`${INPUT_CLASS} h-auto py-3`}
          />
          <p id="ban-reason-help" className="text-sm text-muted">
            {t("reasonHelp", { count: BAN_REASON_MAX_CHARACTERS - [...reason].length })}
          </p>
          <div>
            <button type="submit" disabled={pending} className={BUTTON_CLASS}>
              {t("ban")}
            </button>
          </div>
        </form>
      )}
      {banned && (
        <div>
          <button type="button" onClick={unban} disabled={pending} className={SECONDARY_BUTTON_CLASS}>
            {t("unban")}
          </button>
        </div>
      )}
    </div>
  );
}

export function AccountsSection({ ownId }: { ownId: string }) {
  const t = useTranslations("admin.accounts");
  const [email, setEmail] = useState("");
  const [found, setFound] = useState<Found>({ kind: "idle" });
  const [message, setMessage] = useState<ChangeOutcome | null>(null);

  async function search(address: string) {
    setFound({ kind: "busy" });
    const outcome = await findAccount(address);
    if (outcome.kind === "found") {
      setFound({ kind: "found", account: outcome.account });
      return;
    }
    setFound({ kind: outcome.kind });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    await search(email);
  }

  async function changed(outcome: ChangeOutcome) {
    setMessage(outcome);
    if (found.kind === "found") {
      await search(found.account.email);
    }
  }

  return (
    <section aria-labelledby="admin-accounts-title" className="flex flex-col gap-4 rounded-[18px] bg-panel p-6 sm:p-8">
      <h2 id="admin-accounts-title" className="font-condensed text-[30px] font-bold">
        {t("title")}
      </h2>
      <p className="text-ink2">{t("intro")}</p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <EmailField id="admin-email" label={t("searchLabel")} value={email} onChange={setEmail} />
        <div>
          <button type="submit" disabled={found.kind === "busy"} className={BUTTON_CLASS}>
            {t("search")}
          </button>
        </div>
      </form>
      <FormMessage id="admin-accounts-message" tone="info">
        {found.kind === "missing" && t("missing")}
        {found.kind === "refused" && t("refused")}
        {found.kind === "failed" && t("failed")}
        {message !== null && t(`outcome.${message}`)}
      </FormMessage>
      {found.kind === "found" && <AccountView account={found.account} ownId={ownId} onChanged={changed} />}
    </section>
  );
}
