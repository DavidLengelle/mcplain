import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import { MinusCircleIcon } from "../icons";
import { Chapter, ChapterHeading, LEAD, STRONG_LINE } from "./guide-parts";

const ITEMS = ["languages", "remote", "later", "detours", "nextVersion"] as const;

export function ChapterLimits() {
  const t = useTranslations("home.chapters.limites");

  return (
    <Chapter id="limites">
      <ChapterHeading id="limites" />
      <p className={cn(LEAD, "mt-3.5")}>{t("intro")}</p>
      <ul className="mt-[22px] grid grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-3.5">
        {ITEMS.map((item) => (
          <li key={item} className="flex gap-3.5 rounded-[18px] bg-panel px-5 py-[18px]">
            <MinusCircleIcon className="size-[26px] flex-none stroke-gray" />
            <span>
              <strong className="block text-lg">{t(`items.${item}.title`)}</strong>
              <span className="mt-1 block text-base leading-normal text-ink2">{t(`items.${item}.text`)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className={cn(STRONG_LINE, "mt-5")}>{t("conclusion")}</p>
    </Chapter>
  );
}
