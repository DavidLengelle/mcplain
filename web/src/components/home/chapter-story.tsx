import { useTranslations } from "next-intl";

import {
  GUIDE_SOURCES,
  POSTMARK_CLEAN_VERSIONS_END,
  POSTMARK_CLEAN_VERSIONS_START,
  POSTMARK_TRAPPED_VERSION,
} from "@/lib/constants";
import { cn } from "@/lib/utils";

import { Chapter, ChapterHeading, InlineCode, linkTo, NOTE } from "./guide-parts";

const VERSION = "rounded-lg bg-panel2 px-2.5 py-1.5 font-mono text-sm shadow-[inset_0_0_0_1.5px_var(--line)]";

function VersionTimeline() {
  const t = useTranslations("home.chapters.histoire");

  return (
    <div className="mt-[26px]">
      <ol aria-label={t("versionsLabel")} className="flex flex-wrap items-center gap-2">
        {POSTMARK_CLEAN_VERSIONS_START.map((version) => (
          <li key={version} className={VERSION}>
            {version}
          </li>
        ))}
        <li className="px-1 text-xl leading-none text-muted">
          <span aria-hidden="true">…</span>
          <span className="sr-only">{t("laterVersions")}</span>
        </li>
        {POSTMARK_CLEAN_VERSIONS_END.map((version) => (
          <li key={version} className={VERSION}>
            {version}
          </li>
        ))}
        <li
          data-trapped-version=""
          className="rounded-lg bg-red-note px-2.5 py-1.5 font-mono text-sm font-medium text-red shadow-[var(--red-ring),0_0_14px_var(--red-glow)]"
        >
          {POSTMARK_TRAPPED_VERSION}
        </li>
      </ol>
      <div className="mt-2.5 flex flex-wrap justify-between gap-x-5 gap-y-1 text-[15px]">
        <span className="text-ink2">{t("cleanCaption")}</span>
        <span className="font-semibold text-red">{t("trappedCaption")}</span>
      </div>
    </div>
  );
}

export function ChapterStory() {
  const t = useTranslations("home.chapters.histoire");

  return (
    <Chapter id="histoire" className="rounded-[26px] bg-panel p-5 sm:p-8">
      <ChapterHeading id="histoire" />
      <div className="mt-4 flex flex-wrap gap-x-10 gap-y-5">
        <p className="min-w-0 flex-[1_1_360px] text-lg leading-[1.6]">{t.rich("p1", { code: InlineCode })}</p>
        <p className="min-w-0 flex-[1_1_360px] text-lg leading-[1.6]">{t("p2")}</p>
      </div>
      <VersionTimeline />
      <div className="mt-6 rounded-2xl bg-panel2 px-5 py-[18px]">
        <h3 className="font-condensed text-xl font-bold tracking-[0.08em]">{t("lessonTitle")}</h3>
        <p className="mt-1.5 text-[17px] leading-[1.55]">{t("lesson")}</p>
      </div>
      <p className={cn(NOTE, "mt-3.5")}>
        {t.rich("sources", {
          postmark: linkTo(GUIDE_SOURCES.postmark),
          darkreading: linkTo(GUIDE_SOURCES.darkReading),
          hackernews: linkTo(GUIDE_SOURCES.hackerNews),
        })}
      </p>
    </Chapter>
  );
}
