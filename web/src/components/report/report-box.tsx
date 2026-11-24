"use client";

import { useTranslations } from "next-intl";
import { useId, useState, type FormEvent } from "react";

import { BUTTON_CLASS, FormMessage, INPUT_CLASS, SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { useResetTime } from "@/components/quota-counter";
import { useVisitor } from "@/components/visitor-context";
import {
  characterCount,
  COMMENT_MAX_CHARACTERS,
  REPORT_KINDS,
  sendReport,
  type ReportKind,
  type SendOutcome,
} from "@/lib/visitor-reports";

type Failure = Exclude<SendOutcome, { kind: "sent" }> | { kind: "no_kind" };

function FailureText({ failure }: { failure: Failure }) {
  const t = useTranslations("reportBox.errors");
  const resetTime = useResetTime();
  if (failure.kind === "limit") {
    if (failure.resetsAt === null) {
      return <>{t("limitTomorrow")}</>;
    }
    return <>{t("limit", { time: resetTime(failure.resetsAt) })}</>;
  }
  return <>{t(failure.kind)}</>;
}

export function ReportBox({ analysisId }: { analysisId: string }) {
  const t = useTranslations("reportBox");
  const { solveAltcha } = useVisitor();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ReportKind | null>(null);
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const remaining = COMMENT_MAX_CHARACTERS - characterCount(comment);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (kind === null) {
      setFailure({ kind: "no_kind" });
      return;
    }
    setPending(true);
    setFailure(null);
    const altcha = await solveAltcha();
    if (altcha === null) {
      setPending(false);
      setFailure({ kind: "altcha" });
      return;
    }
    const outcome = await sendReport(analysisId, kind, comment, altcha);
    setPending(false);
    if (outcome.kind === "sent") {
      setSent(true);
      return;
    }
    setFailure(outcome);
  }

  function close() {
    setOpen(false);
    setFailure(null);
  }

  let sendLabel = t("send");
  if (pending) {
    sendLabel = t("sending");
  }

  return (
    <section aria-labelledby={`${formId}-title`} data-report-box="" className="flex flex-col gap-4 rounded-[18px] bg-panel p-5 sm:p-6">
      <h2 id={`${formId}-title`} className="font-condensed text-[26px] leading-tight font-bold">
        {t("title")}
      </h2>
      {sent && (
        <p role="status" data-report-thanks="" className="font-semibold text-ink">
          {t("thanks")}
        </p>
      )}
      {!sent && !open && (
        <div className="flex flex-col items-start gap-3">
          <p className="max-w-[60ch] text-ink2">{t("intro")}</p>
          <button
            type="button"
            aria-expanded={false}
            aria-controls={`${formId}-form`}
            onClick={() => setOpen(true)}
            data-report-open=""
            className={SECONDARY_BUTTON_CLASS}
          >
            {t("open")}
          </button>
        </div>
      )}
      {!sent && open && (
        <form id={`${formId}-form`} onSubmit={submit} noValidate className="flex flex-col gap-4">
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-[15px] font-semibold text-ink">{t("legend")}</legend>
            {REPORT_KINDS.map((item) => (
              <label
                key={item}
                className="flex min-h-11 cursor-pointer items-start gap-3 rounded-[12px] bg-panel2 p-3 has-[:checked]:outline-2 has-[:checked]:outline-accent"
              >
                <input
                  type="radio"
                  name={`${formId}-kind`}
                  value={item}
                  checked={kind === item}
                  onChange={() => setKind(item)}
                  data-report-kind={item}
                  className="mt-1 size-5 shrink-0 accent-accent"
                />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="font-semibold text-ink">{t(`kinds.${item}.label`)}</span>
                  <span className="text-sm text-ink2">{t(`kinds.${item}.hint`)}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${formId}-comment`} className="text-[15px] font-semibold text-ink">
              {t("commentLabel")}
            </label>
            <textarea
              id={`${formId}-comment`}
              name="comment"
              value={comment}
              rows={4}
              maxLength={COMMENT_MAX_CHARACTERS}
              aria-describedby={`${formId}-help ${formId}-count`}
              onChange={(event) => setComment(event.target.value)}
              data-report-comment=""
              className={`${INPUT_CLASS} h-auto py-3`}
            />
            <p id={`${formId}-help`} className="text-sm text-muted">
              {t("commentHelp")}
            </p>
            <p id={`${formId}-count`} data-report-count="" className="text-sm text-muted tabular-nums">
              {t("remaining", { count: Math.max(0, remaining) })}
            </p>
          </div>
          <FormMessage id={`${formId}-message`} tone="error">
            {failure !== null && <FailureText failure={failure} />}
          </FormMessage>
          <div className="flex flex-wrap gap-3">
            <button type="submit" disabled={pending} data-report-send="" className={BUTTON_CLASS}>
              {sendLabel}
            </button>
            <button type="button" disabled={pending} onClick={close} className={SECONDARY_BUTTON_CLASS}>
              {t("cancel")}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
