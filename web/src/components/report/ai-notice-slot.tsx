"use client";

import { useLocale, useTranslations } from "next-intl";

import type { FallbackNotice, NoticeAnswer, NoticeContent } from "@/lib/ai-text";
import type { Message } from "@/lib/analysis";
import { joinList } from "@/lib/report";

import { EngineText, useEngineString } from "../engine-text";
import { InfoIcon } from "../icons";
import { RawText } from "../raw-text";

export const NOTICE_HEADING_ID = "notice-heading";
const CAN_CODE = "ai.notice.fallback.can";

function CanLine({ actions }: { actions: string[] }) {
  const t = useTranslations("engine");
  const engine = useEngineString();
  const locale = useLocale();
  const phrases = actions.map((code) => engine(code));
  if (!t.has(CAN_CODE as never)) {
    return <EngineText code={CAN_CODE} />;
  }
  return <>{t(CAN_CODE as never, { actions: joinList(locale, phrases) } as never)}</>;
}

function FallbackLine({ message, actions }: { message: Message; actions: string[] }) {
  if (message.code === CAN_CODE) {
    return <CanLine actions={actions} />;
  }
  return <EngineText code={message.code} params={message.params} />;
}

function FallbackText({ fallback }: { fallback: FallbackNotice }) {
  return (
    <div data-notice-fallback={fallback.variant} className="flex flex-col gap-1 text-lg leading-[1.45]">
      {fallback.messages.map((message) => (
        <p key={message.code}>
          <FallbackLine message={message} actions={fallback.actions} />
        </p>
      ))}
    </div>
  );
}

function AiAlert({ text }: { text: string }) {
  const t = useTranslations("aiNotice");

  return (
    <div role="note" data-ai-alert="" className="mt-4 flex gap-3 rounded-[14px] bg-panel2 px-[18px] py-4">
      <InfoIcon className="mt-0.5 size-5 flex-none stroke-ink2" />
      <div>
        <strong className="block font-condensed text-lg font-bold tracking-[0.06em] text-ink">{t("alertLabel")}</strong>
        <p className="mt-1 text-base leading-normal text-ink2">
          <RawText value={text} limit={400} expandable={false} className="font-sans" />
        </p>
      </div>
    </div>
  );
}

function AiContent({ content }: { content: NoticeContent }) {
  const t = useTranslations("aiNotice");

  return (
    <div data-notice-ai="">
      <span className="inline-block rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-on-accent">
        {t("automatic")}
      </span>
      <p className="mt-2.5 text-lg leading-[1.45]">
        <RawText value={content.summary} limit={800} expandable={false} className="font-sans" />
      </p>
      {content.use_cases.length > 0 && (
        <div className="mt-3">
          <p className="font-condensed text-sm font-semibold tracking-[0.1em] text-accent">{t("useCases")}</p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-base leading-normal text-ink2">
            {content.use_cases.map((useCase, index) => (
              <li key={index}>
                <RawText value={useCase} limit={300} expandable={false} className="font-sans" />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-sm leading-normal text-muted">{t("disclaimer")}</p>
      {content.alert !== null && <AiAlert text={content.alert} />}
    </div>
  );
}

function Pending() {
  const t = useTranslations("aiNotice");

  return (
    <p role="status" data-notice-pending="" className="mt-3 flex items-center gap-2 text-sm text-muted">
      <span aria-hidden="true" className="size-2 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
      {t("pending")}
    </p>
  );
}

export function AiNoticeSlot({ answer, waiting }: { answer: NoticeAnswer | null; waiting: boolean }) {
  const t = useTranslations("aiNotice");
  if (answer === null) {
    return null;
  }
  const content = answer.content;

  return (
    <section aria-labelledby={NOTICE_HEADING_ID} data-notice={answer.status} className="rounded-2xl bg-panel px-[22px] py-5">
      <h2 id={NOTICE_HEADING_ID} className="mb-2.5 font-condensed text-2xl font-bold tracking-[0.08em]">
        {t("heading")}
      </h2>
      {content !== null && <AiContent content={content} />}
      {content === null && answer.fallback !== null && <FallbackText fallback={answer.fallback} />}
      {waiting && <Pending />}
      {answer.resume !== null && (
        <p data-notice-resume={answer.resume} className="mt-3 text-sm text-muted">
          {t(`paused.${answer.resume}`)}
        </p>
      )}
    </section>
  );
}
