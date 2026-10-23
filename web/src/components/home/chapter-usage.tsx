import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { LampIcon, MailIcon } from "../icons";
import { CARD_TITLE, Chapter, ChapterHeading, LEAD, STRONG_LINE } from "./guide-parts";

const ICON = "size-7 stroke-accent";

const CARDS: { key: string; icon: ReactNode }[] = [
  { key: "files", icon: <LampIcon lamp="files_read" className={ICON} /> },
  { key: "internet", icon: <LampIcon lamp="internet" className={ICON} /> },
  { key: "messages", icon: <MailIcon className={ICON} /> },
  { key: "commands", icon: <LampIcon lamp="commands" className={ICON} /> },
];

export function ChapterUsage() {
  const t = useTranslations("home.chapters.usage");

  return (
    <Chapter id="usage">
      <ChapterHeading id="usage" />
      <p className={cn(LEAD, "mt-3.5")}>{t("intro")}</p>
      <div className="mt-[22px] grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-3.5">
        {CARDS.map((card) => (
          <div key={card.key} className="rounded-[18px] bg-panel px-[22px] py-5">
            {card.icon}
            <h3 className={cn(CARD_TITLE, "mt-2.5")}>{t(`cards.${card.key}.title`)}</h3>
            <p className="mt-1.5 text-base leading-normal text-ink2">{t(`cards.${card.key}.text`)}</p>
          </div>
        ))}
      </div>
      <p className={cn(STRONG_LINE, "mt-5")}>{t("conclusion")}</p>
    </Chapter>
  );
}
