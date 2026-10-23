import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import { AnalyzeLink } from "./analyze-link";
import { Chapter, ChapterHeading, LEAD } from "./guide-parts";

const STEPS = ["check", "publisher", "pin", "minimum", "read"] as const;

const CODE = "block rounded-lg bg-code-bg px-3 py-2 font-mono text-sm text-ink [overflow-wrap:anywhere]";

function PinExamples() {
  const t = useTranslations("home.chapters.proteger.steps.pin");

  return (
    <>
      <code className={cn(CODE, "mt-2.5")}>{t("npx")}</code>
      <code className={cn(CODE, "mt-1.5")}>{t("uvx")}</code>
      <p className="mt-2 text-[15px] leading-normal text-muted">{t("after")}</p>
    </>
  );
}

export function ChapterProtect() {
  const t = useTranslations("home.chapters.proteger");

  return (
    <Chapter id="proteger">
      <ChapterHeading id="proteger" />
      <p className={cn(LEAD, "mt-3.5")}>{t("intro")}</p>
      <ol className="mt-[22px] grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-3.5">
        {STEPS.map((step, index) => (
          <li
            key={step}
            data-step={step}
            className={cn("rounded-[18px] bg-panel px-[22px] py-5", step === "check" && "shadow-sel-ring")}
          >
            <span aria-hidden="true" className="font-condensed text-[44px] leading-none font-bold text-accent">
              {index + 1}
            </span>
            <h3 className="mt-2 font-condensed text-[23px] font-bold">{t(`steps.${step}.title`)}</h3>
            <p className="mt-1.5 text-base leading-[1.55] text-ink2">{t(`steps.${step}.text`)}</p>
            {step === "check" && (
              <AnalyzeLink className="mt-2.5 inline-flex min-h-11 items-center text-base font-semibold text-accent underline underline-offset-2 hover:text-accent-hover">
                {t("steps.check.link")}
              </AnalyzeLink>
            )}
            {step === "pin" && <PinExamples />}
          </li>
        ))}
      </ol>
    </Chapter>
  );
}
