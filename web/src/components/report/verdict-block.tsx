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

export function MessageText({ message }: { message: Message | null }) {
  if (message === null) {
    return null;
  }
  return <EngineText code={message.code} params={message.params} />;
}

export function canRetry(analysis: AnalysisView, result: AnalysisResult): boolean {
  return analysis.state === "failed" || RETRY_CASES.has(result.verdict.gray_case ?? "");
}

export type VerdictSize = "full" | "compact";

type VerdictFrameProps = {
  color: VerdictColor;
  title: ReactNode;
  children?: ReactNode;
  size?: VerdictSize;
  titleId?: string;
};

const FRAME: Record<VerdictSize, string> = {
  full: "gap-x-12 gap-y-6 px-6 py-7 sm:px-8",
  compact: "gap-x-11 gap-y-5 px-5 py-6 sm:px-[30px] sm:py-[26px]",
};

const WORD: Record<VerdictSize, string> = {
  full: "text-[44px] sm:text-[56px]",
  compact: "text-[44px] sm:text-[52px]",
};

const TITLE: Record<VerdictSize, string> = {
  full: "mt-3.5 mb-2 text-[28px] leading-tight",
  compact: "mt-3 mb-2 text-[25px] leading-[1.2]",
};

function VerdictTitle({ size, id, children }: { size: VerdictSize; id: string; children: ReactNode }) {
  const className = cn("font-semibold", TITLE[size]);
  if (size === "compact") {
    return (
      <h3 id={id} className={className}>
        {children}
      </h3>
    );
  }
  return (
    <h1 id={id} className={className}>
      {children}
    </h1>
  );
}

export function VerdictFrame({ color, title, children, size = "full", titleId = VERDICT_TITLE_ID }: VerdictFrameProps) {
  const t = useTranslations("verdict");
  const word = t(`word.${color}`);

  return (
    <section
      aria-labelledby={titleId}
      data-verdict={color}
      className={cn("flex flex-wrap items-center rounded-[22px] bg-panel", FRAME[size])}
    >
      <Gauge color={color} word={word} size={size} />
      <div className={cn("min-w-0", size === "full" && "flex-[999_1_420px]", size === "compact" && "flex-[999_1_380px]")}>
        <p className="font-condensed text-[15px] font-semibold tracking-[0.14em] text-muted">{t("heading")}</p>
        <p
          data-verdict-word={color}
          className={cn("mt-1 font-condensed leading-none font-bold tracking-[0.02em]", WORD[size], WORD_COLORS[color])}
        >
          {word}
        </p>
        <VerdictTitle size={size} id={titleId}>
          {title}
        </VerdictTitle>
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
