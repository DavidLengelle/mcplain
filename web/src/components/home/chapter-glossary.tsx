import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import { Chapter, ChapterHeading } from "./guide-parts";

const TERMS = ["mcp", "server", "tool", "description", "package", "runners", "version", "static"] as const;

const CODE_TERMS = new Set<string>(["runners"]);

export function ChapterGlossary() {
  const t = useTranslations("home.chapters.lexique");

  return (
    <Chapter id="lexique">
      <ChapterHeading id="lexique" />
      <dl className="mt-[22px] grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-3">
        {TERMS.map((term) => (
          <div key={term} className="rounded-2xl bg-panel px-5 py-4">
            <dt
              className={cn(
                CODE_TERMS.has(term) && "font-mono text-[19px] font-medium",
                !CODE_TERMS.has(term) && "font-condensed text-[21px] font-bold",
              )}
            >
              {t(`terms.${term}.term`)}
            </dt>
            <dd className="mt-1 text-base leading-normal text-ink2">{t(`terms.${term}.definition`)}</dd>
          </div>
        ))}
      </dl>
    </Chapter>
  );
}
