"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { BUTTON_CLASS, FormMessage, INPUT_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import {
  addCreditEntry,
  CREDIT_NOTE_MAX_CHARACTERS,
  deleteCreditEntry,
  parseAmount,
  readCredit,
  readSpend,
  type ActionOutcome,
  type Credit,
  type Days,
  type Spend,
  type SpendDay,
} from "@/lib/admin-dashboard";

import { useOutcomeText } from "./outcome";
import { Bar, BarList, BarRow, ConfirmButton, DialCard, DialMessage, Empty, useDay, useDial, useDollars, useMoment } from "./parts";

function Gauge({ label, value, limit, reached, testId }: { label: string; value: number; limit: number; reached: boolean; testId: string }) {
  const t = useTranslations("admin.dashboard.spend");
  const dollars = useDollars();
  const shown = t("ofLimit", { value: dollars(value), limit: dollars(limit) });
  return (
    <div data-testid={testId} className="flex flex-col gap-1.5 rounded-[14px] bg-panel2 p-4">
      <p className="text-[15px] font-semibold text-muted">{label}</p>
      <p className="font-condensed text-[28px] leading-none font-bold text-ink tabular-nums">{shown}</p>
      <Bar value={value} max={limit} label={`${label} : ${shown}`} alert={reached} />
      {reached && <p className="font-semibold text-warn-text">{t("reached")}</p>}
    </div>
  );
}

function paidDay(item: SpendDay): boolean {
  return item.paidCalls > 0 || item.costUsd > 0;
}

function WriterState({ spend }: { spend: Spend }) {
  const t = useTranslations("admin.dashboard.writer");
  const moment = useMoment();
  if (spend.writer.disabledReason !== null) {
    return (
      <p data-testid="admin-writer-state" className="font-semibold text-warn-text">
        {t("disabled", { reason: spend.writer.disabledReason })}
      </p>
    );
  }
  if (spend.writer.pausedUntil !== null) {
    return (
      <p data-testid="admin-writer-state" className="font-semibold text-warn-text">
        {t("paused", { until: moment(spend.writer.pausedUntil) })}
      </p>
    );
  }
  return null;
}

export function SpendDial({ days, refresh }: { days: Days; refresh: number }) {
  const t = useTranslations("admin.dashboard.spend");
  const read = useDial(readSpend, days, refresh);
  const dollars = useDollars();
  const day = useDay();
  if (read === null || read.kind !== "ready") {
    return (
      <DialCard id="admin-spend-title" title={t("title")} testId="admin-spend">
        <DialMessage read={read} />
      </DialCard>
    );
  }
  const spend = read.value;
  const dayDetail = (item: SpendDay) => {
    if (!paidDay(item)) {
      return undefined;
    }
    return t("dayDetail", { notice: dollars(item.noticeUsd), translation: dollars(item.translationUsd), calls: item.paidCalls });
  };
  const highest = Math.max(0, ...spend.perDay.map((item) => item.costUsd));
  const quietDays = spend.perDay.filter((item) => !paidDay(item)).length;
  return (
    <DialCard id="admin-spend-title" title={t("title")} testId="admin-spend">
      <div className="grid gap-3 sm:grid-cols-2">
        <Gauge label={t("today")} value={spend.todayUsd} limit={spend.dailyFuseUsd} reached={spend.fuseReached} testId="admin-spend-today" />
        <Gauge label={t("month")} value={spend.monthUsd} limit={spend.monthlyBudgetUsd} reached={spend.budgetReached} testId="admin-spend-month" />
      </div>
      <WriterState spend={spend} />
      <p className="text-ink2" data-testid="admin-spend-period">
        {t("period", { days, notice: dollars(spend.noticeUsd), translation: dollars(spend.translationUsd), calls: spend.paidCalls })}
      </p>
      <h4 className="font-semibold text-ink">{t("perDay")}</h4>
      <BarList testId="admin-spend-days">
        {spend.perDay.map((item) => (
          <BarRow
            key={item.day}
            label={day(item.day)}
            value={item.costUsd}
            max={highest}
            shown={dollars(item.costUsd)}
            detail={dayDetail(item)}
          />
        ))}
      </BarList>
      {quietDays > 0 && (
        <p className="text-sm text-muted" data-testid="admin-spend-quiet-days">
          {t("quietDays", { count: quietDays })}
        </p>
      )}
      <p className="text-sm text-muted">{t("source")}</p>
    </DialCard>
  );
}

function readCreditOnce(): ReturnType<typeof readCredit> {
  return readCredit();
}

function entryKind(kind: string): "statement" | "top_up" {
  if (kind === "top_up") {
    return "top_up";
  }
  return "statement";
}

function Entries({ credit, onChanged }: { credit: Credit; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.balance");
  const dollars = useDollars();
  const moment = useMoment();
  if (credit.entries.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-2">
      <h4 className="font-semibold text-ink">{t("entries")}</h4>
      <ul data-testid="admin-credit-entries" className="flex flex-col gap-2">
        {credit.entries.map((entry) => (
          <li key={entry.id} className="flex flex-col gap-1 rounded-[12px] bg-panel2 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4">
            <span className="text-sm text-muted">{moment(entry.createdAt)}</span>
            <span className="font-semibold text-ink">{t(`kind.${entryKind(entry.kind)}`)}</span>
            <span className="font-semibold text-ink tabular-nums">{dollars(entry.amountUsd)}</span>
            {entry.note !== null && (
              <span className="min-w-0 break-words text-ink2">
                <RawText value={entry.note} />
              </span>
            )}
            {entry.id === credit.lastEntryId && (
              <span className="sm:ml-auto">
                <ConfirmButton
                  testId="admin-credit-delete"
                  label={t("delete")}
                  question={t("deleteQuestion")}
                  confirm={t("deleteConfirm")}
                  onConfirm={async () => onChanged(await deleteCreditEntry(entry.id))}
                />
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EntryForm({ onChanged }: { onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.balance");
  const [kind, setKind] = useState<"statement" | "top_up">("statement");
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = parseAmount(typed);
    if (amount === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setPending(true);
    const outcome = await addCreditEntry(kind, amount, note);
    setPending(false);
    if (outcome.kind === "done") {
      setTyped("");
      setNote("");
    }
    onChanged(outcome);
  }

  return (
    <form onSubmit={submit} data-testid="admin-credit-form" className="flex flex-col gap-3 rounded-[14px] bg-panel2 p-4">
      <h4 className="font-semibold text-ink">{t("formTitle")}</h4>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[15px] font-semibold text-ink">{t("kindLabel")}</legend>
        {(["statement", "top_up"] as const).map((choice) => (
          <label key={choice} className="flex min-h-11 items-center gap-3 text-ink">
            <input type="radio" name="credit-kind" value={choice} checked={kind === choice} onChange={() => setKind(choice)} className="size-5 accent-accent" />
            <span>{t(`kindHelp.${choice}`)}</span>
          </label>
        ))}
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="credit-amount" className="text-[15px] font-semibold text-ink">
          {t("amountLabel")}
        </label>
        <input
          id="credit-amount"
          name="credit-amount"
          inputMode="decimal"
          autoComplete="off"
          required
          value={typed}
          aria-invalid={invalid}
          aria-describedby="credit-amount-help"
          onChange={(event) => setTyped(event.target.value)}
          className={INPUT_CLASS}
        />
        <p id="credit-amount-help" className="text-sm text-muted">
          {t("amountHelp")}
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="credit-note" className="text-[15px] font-semibold text-ink">
          {t("noteLabel")}
        </label>
        <input
          id="credit-note"
          name="credit-note"
          autoComplete="off"
          maxLength={CREDIT_NOTE_MAX_CHARACTERS}
          value={note}
          aria-describedby="credit-note-help"
          onChange={(event) => setNote(event.target.value)}
          className={INPUT_CLASS}
        />
        <p id="credit-note-help" className="text-sm text-muted">
          {t("noteHelp", { count: CREDIT_NOTE_MAX_CHARACTERS - [...note].length })}
        </p>
      </div>
      <FormMessage id="credit-amount-error" tone="error">
        {invalid && t("amountInvalid")}
      </FormMessage>
      <div>
        <button type="submit" disabled={pending} className={BUTTON_CLASS}>
          {t("add")}
        </button>
      </div>
    </form>
  );
}

function BalanceFigure({ credit }: { credit: Credit }) {
  const t = useTranslations("admin.dashboard.balance");
  const dollars = useDollars();
  const moment = useMoment();
  if (credit.balanceUsd === null) {
    return (
      <p data-testid="admin-balance-empty" className="font-semibold text-ink">
        {t("noStatement")}
      </p>
    );
  }
  return (
    <div data-testid="admin-balance" className="flex flex-col gap-1.5 rounded-[14px] bg-panel2 p-4">
      <p className="text-[15px] font-semibold text-muted">{t("estimated")}</p>
      <p data-testid="admin-balance-amount" className="font-condensed text-[34px] leading-none font-bold text-ink tabular-nums">
        {dollars(credit.balanceUsd)}
      </p>
      {credit.low && (
        <p data-testid="admin-balance-low" className="font-semibold text-warn-text">
          {t("low", { threshold: dollars(credit.thresholdUsd) })}
        </p>
      )}
      <p className="text-ink2">
        {t("formula", { statement: dollars(credit.statementUsd ?? 0), topUps: dollars(credit.topUpsUsd), spent: dollars(credit.spentUsd) })}
      </p>
      <p className="text-ink2">{t("statementAt", { date: moment(credit.statementAt) })}</p>
      <p className="text-sm text-muted">{t("estimate")}</p>
      {credit.alertSentAt !== null && <p className="text-sm text-muted">{t("mailSent", { date: moment(credit.alertSentAt) })}</p>}
      {credit.alertSentAt === null && <p className="text-sm text-muted">{t("mailArmed", { threshold: dollars(credit.thresholdUsd) })}</p>}
    </div>
  );
}

export function BalanceDial({ days, refresh, onChanged }: { days: Days; refresh: number; onChanged: () => void }) {
  const t = useTranslations("admin.dashboard.balance");
  const read = useDial(readCreditOnce, days, refresh);
  const outcomeText = useOutcomeText();
  const [outcome, setOutcome] = useState<ActionOutcome | null>(null);

  function changed(result: ActionOutcome) {
    setOutcome(result);
    onChanged();
  }

  return (
    <DialCard id="admin-balance-title" title={t("title")} testId="admin-balance-dial">
      {read !== null && read.kind === "ready" && <BalanceFigure credit={read.value} />}
      {(read === null || read.kind !== "ready") && <DialMessage read={read} />}
      <EntryForm onChanged={changed} />
      <FormMessage id="admin-credit-message" tone="info">
        {outcome !== null && outcomeText(outcome)}
      </FormMessage>
      {read !== null && read.kind === "ready" && <Entries credit={read.value} onChanged={changed} />}
      {read !== null && read.kind === "ready" && read.value.entries.length === 0 && <Empty>{t("noEntry")}</Empty>}
    </DialCard>
  );
}
