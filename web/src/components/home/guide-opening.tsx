import { useTranslations } from "next-intl";

import { CHAPTER_IDS } from "@/lib/constants";
import { cn } from "@/lib/utils";

import { BookIcon } from "../icons";
import { CONTAINER } from "../page-container";
import { chapterNumber, SECTION_TITLE } from "./guide-parts";

export const GUIDE_TITLE_ID = "h-guide";

export function GuideOpening() {
  const t = useTranslations("home.guide");
  const chapters = useTranslations("home.chapters");

  return (
    <nav aria-labelledby={GUIDE_TITLE_ID} data-guide-opening="" className={cn(CONTAINER, "pt-16 text-center")}>
      <div className="flex items-center gap-4">
        <span aria-hidden="true" className="h-0.5 flex-1 bg-btn-border" />
        <span className="inline-flex items-center gap-2.5 font-condensed text-[17px] font-bold tracking-[0.18em] text-ink2">
          <BookIcon className="size-6 stroke-accent" />
          {t("label")}
        </span>
        <span aria-hidden="true" className="h-0.5 flex-1 bg-btn-border" />
      </div>
      <h2 id={GUIDE_TITLE_ID} className={cn(SECTION_TITLE, "mt-7")}>
        {t("title")}
      </h2>
      <p className="mx-auto mt-3 max-w-[60ch] text-[19px] leading-[1.6] text-ink2">{t("intro")}</p>
      <ol className="mt-[22px] flex flex-wrap justify-center gap-2">
        {CHAPTER_IDS.map((id) => (
          <li key={id}>
            <a
              href={`#${id}`}
              data-toc={id}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-panel px-3.5 text-[15px] text-ink no-underline transition-colors hover:bg-row-hover motion-reduce:transition-none"
            >
              <span className="font-condensed font-bold text-accent">{chapterNumber(id)}</span>
              {chapters(`${id}.toc`)}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
