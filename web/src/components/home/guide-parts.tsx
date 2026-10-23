import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { CHAPTER_IDS, type ChapterId } from "@/lib/constants";
import { toolNumber } from "@/lib/report";
import { cn } from "@/lib/utils";

export const SCROLL_UNDER_HEADER = "scroll-mt-[calc(var(--header-height,6rem)+1rem)]";
export const EYEBROW = "font-condensed text-[15px] font-semibold tracking-[0.14em] text-accent";
export const SECTION_TITLE = "font-condensed text-[38px] leading-[1.05] font-bold sm:text-[44px]";
export const SUBHEADING = "font-condensed text-[22px] font-bold tracking-[0.08em]";
export const CARD_TITLE = "font-condensed text-[22px] font-bold";
export const LEAD = "max-w-[64ch] text-[19px] leading-[1.6] text-ink2";
export const NOTE = "text-sm leading-[1.55] text-muted";
export const STRONG_LINE = "text-[19px] leading-[1.55] font-semibold";
export const DEMO_BADGE = "rounded-md bg-demo-bg font-condensed font-semibold tracking-[0.1em] text-demo-fg";

export function chapterNumber(id: ChapterId): string {
  return toolNumber(CHAPTER_IDS.indexOf(id));
}

export function chapterHeadingId(id: ChapterId): string {
  return `h-${id}`;
}

export function Bold(chunks: ReactNode) {
  return <strong className="font-bold text-ink">{chunks}</strong>;
}

export function InlineCode(chunks: ReactNode) {
  return <code className="font-mono text-base">{chunks}</code>;
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline underline-offset-2 hover:text-accent-hover"
    >
      {children}
    </a>
  );
}

export function linkTo(href: string) {
  return function SourceLink(chunks: ReactNode) {
    return <ExternalLink href={href}>{chunks}</ExternalLink>;
  };
}

export function Chapter({ id, className, children }: { id: ChapterId; className?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={chapterHeadingId(id)} data-chapter={id} className={cn(SCROLL_UNDER_HEADER, className)}>
      {children}
    </section>
  );
}

export function ChapterHeading({ id, badge }: { id: ChapterId; badge?: string }) {
  const guide = useTranslations("home.guide");
  const t = useTranslations(`home.chapters.${id}`);

  return (
    <>
      <p className={EYEBROW}>{guide("eyebrow", { number: chapterNumber(id), label: t("eyebrow") })}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 id={chapterHeadingId(id)} className={SECTION_TITLE}>
          {t("title")}
        </h2>
        {badge !== undefined && <span className={cn(DEMO_BADGE, "px-2.5 py-[3px] text-sm")}>{badge}</span>}
      </div>
    </>
  );
}
