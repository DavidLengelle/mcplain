"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { FormMessage, LINK_CLASS, SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { Link } from "@/i18n/navigation";
import { markAlertRead, rerunAnalysis, retryText, type ActionOutcome, type AiHealth, type AiText, type Analyses, type Read } from "@/lib/admin-dashboard";
import { cn } from "@/lib/utils";

import { useOutcomeText } from "./outcome";
import { BarList, BarRow, ConfirmButton, DialCard, DialMessage, Empty, useDay, useMoment } from "./parts";

const RETRYABLE = new Set(["rejected", "failed"]);

function textKind(kind: string): "notice" | "translation" {
  if (kind === "translation") {
    return "translation";
  }
  return "notice";
}

function refundKey(refund: string): "keep" | "give_back" {
  if (refund === "keep") {
    return "keep";
  }
  return "give_back";
}

function reasonsLine(reasons: { code: string; count: number }[]): string | undefined {
  if (reasons.length === 0) {
    return undefined;
  }
  return reasons.map((reason) => `${reason.code} ${reason.count}`).join(" · ");
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function AlertsDial({ health, onChanged }: { health: AiHealth; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.alerts");
  const moment = useMoment();
  if (health.alerts.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  return (
    <ul data-testid="admin-alerts" className="flex flex-col gap-2">
      {health.alerts.map((alert) => {
        const unread = alert.readAt === null;
        return (
          <li key={alert.id} className={cn("flex flex-col gap-1.5 rounded-[12px] bg-panel2 p-3", unread && "border-l-4 border-warn")}>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-mono font-semibold text-ink">
                <RawText value={alert.code} />
              </span>
              {unread && <span className="font-semibold text-warn-text">{t("unread")}</span>}
              {!unread && <span className="text-muted">{t("read", { date: moment(alert.readAt) })}</span>}
            </p>
            <p className="text-sm text-ink2">
              {t("detail", { date: moment(alert.createdAt), kind: alert.kind ?? "-", status: alert.status ?? "-" })}
            </p>
            {alert.emailedAt !== null && <p className="text-sm text-muted">{t("emailed", { date: moment(alert.emailedAt) })}</p>}
            {unread && (
              <div>
                <button type="button" onClick={() => void markAlertRead(alert.id).then(onChanged)} className={SECONDARY_BUTTON_CLASS}>
                  {t("markRead")}
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function RejectionsDial({ health }: { health: AiHealth }) {
  const t = useTranslations("admin.dashboard.rejections");
  const format = useFormatter();
  const day = useDay();
  const totals = health.perDay.map((item) => sum(item.reasons.map((reason) => reason.count)));
  const highest = Math.max(0, ...totals);
  let rate = t("rateNone");
  if (health.encoding.rate !== null) {
    rate = t("rate", {
      rate: format.number(health.encoding.rate, { style: "percent", maximumFractionDigits: 1 }),
      rejected: health.encoding.rejected,
      calls: health.encoding.paidNoticeCalls,
    });
  }
  return (
    <>
      <p data-testid="admin-encoding-rate" className="font-semibold text-ink">
        {rate}
      </p>
      {health.reasons.length === 0 && <Empty>{t("none")}</Empty>}
      {health.reasons.length > 0 && (
        <ul data-testid="admin-rejection-reasons" className="flex flex-wrap gap-2">
          {health.reasons.map((reason) => (
            <li key={reason.code} className="rounded-[10px] bg-panel2 px-3 py-1.5 text-ink">
              <span className="font-mono">
                <RawText value={reason.code} />
              </span>{" "}
              <span className="font-semibold tabular-nums">{reason.count}</span>
            </li>
          ))}
        </ul>
      )}
      <h4 className="font-semibold text-ink">{t("perDay")}</h4>
      <BarList testId="admin-rejection-days">
        {health.perDay.map((item, index) => (
          <BarRow
            key={item.day}
            label={day(item.day)}
            value={totals[index] ?? 0}
            max={highest}
            shown={String(totals[index] ?? 0)}
            detail={reasonsLine(item.reasons)}
          />
        ))}
      </BarList>
    </>
  );
}

function TextLine({ text, onChanged }: { text: AiText; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.texts");
  const moment = useMoment();
  return (
    <li className="flex flex-col gap-1.5 rounded-[12px] bg-panel2 p-3">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-ink">
        <span className="font-semibold">{t(`kind.${textKind(text.kind)}`)}</span>
        <span className="font-mono">
          <RawText value={text.lang} />
        </span>
        <span className="font-semibold">{t(`status.${text.status}`)}</span>
        {text.rejectReason !== null && (
          <span className="font-mono">
            <RawText value={text.rejectReason} />
          </span>
        )}
      </p>
      <p className="text-sm text-muted">{moment(text.updatedAt)}</p>
      <div className="flex flex-wrap items-center gap-3">
        {text.analysisId !== null && (
          <Link href={`/analyses/${text.analysisId}`} className={LINK_CLASS}>
            {t("report")}
          </Link>
        )}
        {RETRYABLE.has(text.status) && (
          <ConfirmButton
            testId="admin-text-retry"
            label={t("retry")}
            question={t("retryQuestion")}
            confirm={t("retryConfirm")}
            onConfirm={async () => onChanged(await retryText(text.id))}
          />
        )}
        {text.analysisId !== null && <RerunButton analysisId={text.analysisId} onChanged={onChanged} />}
      </div>
    </li>
  );
}

export function RerunButton({ analysisId, onChanged }: { analysisId: string; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.rerun");
  return (
    <ConfirmButton
      testId="admin-analysis-rerun"
      label={t("label")}
      question={t("question")}
      confirm={t("confirm")}
      onConfirm={async () => onChanged(await rerunAnalysis(analysisId))}
    />
  );
}

function TextsDial({ health, onChanged }: { health: AiHealth; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.texts");
  if (health.texts.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  return (
    <ul data-testid="admin-texts" className="flex flex-col gap-2">
      {health.texts.map((text) => (
        <TextLine key={text.id} text={text} onChanged={onChanged} />
      ))}
    </ul>
  );
}

function FailuresDial({ analyses }: { analyses: Analyses }) {
  const t = useTranslations("admin.dashboard.failures");
  if (analyses.failures.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  const highest = Math.max(0, ...analyses.failures.map((item) => item.count));
  return (
    <BarList testId="admin-failures">
      {analyses.failures.map((item) => (
        <BarRow
          key={item.code}
          label={item.code}
          value={item.count}
          max={highest}
          shown={String(item.count)}
          detail={t(`refund.${refundKey(item.refund)}`)}
          raw
        />
      ))}
    </BarList>
  );
}

export function HealthGroup({ ai, analyses, onChanged }: { ai: Read<AiHealth> | null; analyses: Read<Analyses> | null; onChanged: () => void }) {
  const t = useTranslations("admin.dashboard");
  const outcomeText = useOutcomeText();
  const [outcome, setOutcome] = useState<ActionOutcome | null>(null);

  function changed(result: ActionOutcome) {
    setOutcome(result);
    onChanged();
  }

  return (
    <>
      <FormMessage id="admin-health-message" tone="info">
        {outcome !== null && outcomeText(outcome)}
      </FormMessage>
      <DialCard id="admin-alerts-title" title={t("alerts.title")} testId="admin-alerts-dial">
        {ai !== null && ai.kind === "ready" && <AlertsDial health={ai.value} onChanged={changed} />}
        {(ai === null || ai.kind !== "ready") && <DialMessage read={ai} />}
      </DialCard>
      <DialCard id="admin-rejections-title" title={t("rejections.title")} testId="admin-rejections-dial">
        {ai !== null && ai.kind === "ready" && <RejectionsDial health={ai.value} />}
        {(ai === null || ai.kind !== "ready") && <DialMessage read={ai} />}
      </DialCard>
      <DialCard id="admin-texts-title" title={t("texts.title")} testId="admin-texts-dial">
        <p className="text-ink2">{t("texts.intro")}</p>
        {ai !== null && ai.kind === "ready" && <TextsDial health={ai.value} onChanged={changed} />}
        {(ai === null || ai.kind !== "ready") && <DialMessage read={ai} />}
      </DialCard>
      <DialCard id="admin-failures-title" title={t("failures.title")} testId="admin-failures-dial">
        {analyses !== null && analyses.kind === "ready" && <FailuresDial analyses={analyses.value} />}
        {(analyses === null || analyses.kind !== "ready") && <DialMessage read={analyses} />}
      </DialCard>
    </>
  );
}
