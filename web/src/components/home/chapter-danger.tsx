import { useTranslations } from "next-intl";

import { GUIDE_SOURCES } from "@/lib/constants";
import { cn } from "@/lib/utils";

import { Bold, CARD_TITLE, Chapter, ChapterHeading, DEMO_BADGE, LEAD, linkTo, NOTE, STRONG_LINE, SUBHEADING } from "./guide-parts";

const TRIANGLE = ["data", "untrusted", "exit"] as const;

function PoisonedTool() {
  const t = useTranslations("home.chapters.danger.example");

  return (
    <div className="flex min-w-0 flex-[999_1_460px] flex-col gap-3 rounded-[22px] bg-panel p-4 sm:p-[22px]">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <p className="font-condensed text-lg font-bold tracking-[0.08em]">{t("title")}</p>
        <span className={cn(DEMO_BADGE, "px-2 py-0.5 text-[13px]")}>{t("badge")}</span>
      </div>
      <div className="rounded-[14px] bg-panel2 px-4 py-3.5">
        <p className="text-[13px] font-semibold text-muted">{t("shownLabel")}</p>
        <p className="mt-1.5 text-[17px] leading-normal">{t("shown")}</p>
      </div>
      <div className="rounded-[14px] bg-red-note px-4 py-3.5 shadow-red-ring">
        <p className="text-[13px] font-semibold text-red">{t("readLabel")}</p>
        <p className="mt-1.5 text-[17px] leading-normal">{t("read")}</p>
      </div>
    </div>
  );
}

function LethalTrifecta() {
  const t = useTranslations("home.chapters.danger.triangle");

  return (
    <div className="mt-10">
      <h3 className={SUBHEADING}>{t("heading")}</h3>
      <p className="mt-2.5 max-w-[66ch] text-lg leading-[1.6] text-ink2">{t("intro")}</p>
      <ol className="mt-[18px] grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-3.5">
        {TRIANGLE.map((key, index) => (
          <li key={key} className="rounded-[18px] bg-panel px-[22px] py-5">
            <span
              aria-hidden="true"
              className="flex size-[38px] items-center justify-center rounded-full bg-accent font-condensed text-xl font-bold text-on-accent"
            >
              {index + 1}
            </span>
            <h4 className={cn(CARD_TITLE, "mt-3")}>{t(`${key}.title`)}</h4>
            <p className="mt-1.5 text-base leading-normal text-ink2">{t(`${key}.text`)}</p>
          </li>
        ))}
      </ol>
      <div className="mt-3.5 flex flex-wrap items-center gap-x-[22px] gap-y-2 rounded-[18px] bg-red-note px-6 py-[18px] shadow-red-ring">
        <span className="font-condensed text-[30px] font-bold tracking-[0.04em] text-red">{t("sum")}</span>
        <p className="min-w-0 flex-[1_1_300px] text-lg leading-normal">{t.rich("sumText", { b: Bold })}</p>
      </div>
      <p className={cn(STRONG_LINE, "mt-4")}>{t("rule")}</p>
      <p className={cn(NOTE, "mt-2.5")}>{t.rich("source", { link: linkTo(GUIDE_SOURCES.lethalTrifecta) })}</p>
    </div>
  );
}

export function ChapterDanger() {
  const t = useTranslations("home.chapters.danger");

  return (
    <Chapter id="danger">
      <ChapterHeading id="danger" />
      <p className={cn(LEAD, "mt-3.5")}>{t("intro")}</p>
      <div className="mt-7 flex flex-wrap items-start gap-x-10 gap-y-6">
        <div className="min-w-0 flex-[1_1_340px]">
          <h3 className={SUBHEADING}>{t("trap.heading")}</h3>
          <p className="mt-2.5 text-lg leading-[1.6]">{t("trap.lead")}</p>
          <p className="mt-2.5 text-lg leading-[1.6] text-ink2">{t("trap.text")}</p>
          <p className={cn(NOTE, "mt-3")}>{t.rich("trap.source", { link: linkTo(GUIDE_SOURCES.toolPoisoning) })}</p>
        </div>
        <PoisonedTool />
      </div>
      <LethalTrifecta />
    </Chapter>
  );
}
