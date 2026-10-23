import { useTranslations } from "next-intl";

import { AnalyzeLink } from "./analyze-link";

export const END_TITLE_ID = "h-fin";

export function GuideEnd() {
  const t = useTranslations("home.end");

  return (
    <section
      aria-labelledby={END_TITLE_ID}
      className="flex flex-wrap items-center justify-between gap-x-8 gap-y-[18px] rounded-[26px] bg-panel p-6 sm:p-8"
    >
      <div className="min-w-0 flex-[999_1_380px]">
        <h2 id={END_TITLE_ID} className="font-condensed text-[40px] leading-[1.05] font-bold">
          {t("title")}
        </h2>
        <p className="mt-2 text-lg leading-[1.55] text-ink2">{t("text")}</p>
      </div>
      <AnalyzeLink className="inline-flex min-h-[60px] flex-none items-center rounded-xl bg-accent px-[30px] font-condensed text-[22px] font-bold tracking-[0.06em] text-on-accent no-underline hover:bg-accent-hover">
        {t("link")}
      </AnalyzeLink>
    </section>
  );
}
