import { useTranslations } from "next-intl";

import { TOOL_ZONE_ID } from "@/lib/constants";
import { offLamps } from "@/lib/report";
import { cn } from "@/lib/utils";

import { AnalysisField } from "../analysis-field";
import { CONTAINER } from "../page-container";
import { LampPanel } from "../report/lamp-cluster";
import { EYEBROW, SCROLL_UNDER_HEADER } from "./guide-parts";

export const HERO_TITLE_ID = "h-hero";

const POINTS = ["free", "nothingToInstall", "neverRun"] as const;

export function ToolZone() {
  const t = useTranslations("home.tool");

  return (
    <section
      id={TOOL_ZONE_ID}
      aria-labelledby={HERO_TITLE_ID}
      data-tool-zone=""
      className={cn(SCROLL_UNDER_HEADER, "border-b border-line bg-panel")}
    >
      <div className={cn(CONTAINER, "flex flex-wrap items-center gap-x-14 gap-y-10 pt-10 pb-12 sm:pt-14 sm:pb-16")}>
        <div className="min-w-0 flex-[999_1_520px]">
          <p className={EYEBROW}>{t("eyebrow")}</p>
          <h1
            id={HERO_TITLE_ID}
            className="mt-2.5 font-condensed text-[clamp(42px,6vw,70px)] leading-[1.02] font-bold tracking-[0.01em]"
          >
            {t("title")}
          </h1>
          <p className="mt-[18px] max-w-[56ch] text-xl leading-[1.55] text-ink2">{t("intro")}</p>
          <AnalysisField variant="hero" />
          <ul className="mt-[22px] flex flex-wrap gap-x-[22px] gap-y-2 text-[15px] text-ink2">
            {POINTS.map((point) => (
              <li key={point} className="flex items-center gap-2">
                <span aria-hidden="true" className="size-2 rounded-full bg-accent" />
                {t(`points.${point}`)}
              </li>
            ))}
          </ul>
        </div>
        <LampPanel
          lamps={offLamps()}
          domains={null}
          headingId="hero-lamps"
          headingAs="p"
          status={t("lampsStatus")}
          size="hero"
          className="max-w-[460px] min-w-0 flex-[1_1_340px]"
        >
          <p className="text-[15px] leading-normal text-cluster-muted">{t("lampsSentence")}</p>
        </LampPanel>
      </div>
    </section>
  );
}
