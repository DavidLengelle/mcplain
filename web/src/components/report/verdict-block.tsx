import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { AnalysisResult, AnalysisView, Message, VerdictColor } from "@/lib/analysis";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { Gauge } from "./gauge";
import { RetryButton } from "./retry-button";

export const VERDICT_TITLE_ID = "verdict-title";

const WORD_COLORS: Record<VerdictColor, string> = {
  green: "text-green",
  orange: "text-warn",
  red: "text-red",
  gray: "text-gray",
};

const RETRY_CASES = new Set(["timeout", "error"]);
const JOB_PREFIX = "job.";

function MessageText({ message }: { message: Message | null }) {
  if (message === null) {
    return null;
  }
  return <EngineText code={message.code} params={message.params} />;
}

export function canRetry(analysis: AnalysisView, result: AnalysisResult): boolean {
  return analysis.state === "failed" || RETRY_CASES.has(result.verdict.gray_case ?? "");
}

type VerdictFrameProps = { color: VerdictColor; title: ReactNode; children?: ReactNode };

export function VerdictFrame({ color, title, children }: VerdictFrameProps) {
  const t = useTranslations("verdict");
  const word = t(`word.${color}`);

  return (
    <section
      aria-labelledby={VERDICT_TITLE_ID}
      data-verdict={color}
      className="flex flex-wrap items-center gap-x-12 gap-y-6 rounded-[22px] bg-panel px-6 py-7 sm:px-8"
    >
      <Gauge color={color} word={word} />
      <div className="min-w-0 flex-[999_1_420px]">
        <p className="font-condensed text-[15px] font-semibold tracking-[0.14em] text-muted">{t("heading")}</p>
        <p
          data-verdict-word={color}
          className={cn(
            "mt-1 font-condensed text-[44px] leading-none font-bold tracking-[0.02em] sm:text-[56px]",
            WORD_COLORS[color],
          )}
        >
          {word}
        </p>
        <h1 id={VERDICT_TITLE_ID} className="mt-3.5 mb-2 text-[28px] leading-tight font-semibold">
          {title}
        </h1>
        {children}
      </div>
    </section>
  );
}

export function VerdictBlock({ analysis, result }: { analysis: AnalysisView; result: AnalysisResult }) {
  const verdict = result.verdict;
  const error = result.error;

  return (
    <VerdictFrame color={verdict.color} title={<MessageText message={verdict.title} />}>
      {verdict.summary !== null && (
        <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">
          <MessageText message={verdict.summary} />
        </p>
      )}
      {error !== null && !error.code.startsWith(JOB_PREFIX) && (
        <p className="mt-3 max-w-[60ch] text-ink2">
          <EngineText code={error.code} params={error.params} />
        </p>
      )}
      {verdict.color === "gray" && (
        <p className="mt-3 max-w-[60ch] text-lg font-semibold">
          <EngineText code="verdict.gray.not_safe" />
        </p>
      )}
      {canRetry(analysis, result) && <RetryButton input={analysis.input} select={analysis.select} />}
    </VerdictFrame>
  );
}
