import { useTranslations } from "next-intl";

import { TOP_ID } from "@/lib/constants";

import { ArrowUpIcon } from "../icons";

export function BackToTop() {
  const t = useTranslations("report");

  return (
    <a
      href={`#${TOP_ID}`}
      aria-label={t("backToTop")}
      data-back-to-top=""
      className="fixed right-4 bottom-4 z-30 flex size-14 items-center justify-center rounded-full bg-accent no-underline shadow-arrow sm:right-6 sm:bottom-6"
    >
      <ArrowUpIcon className="size-6 stroke-on-accent" />
    </a>
  );
}
