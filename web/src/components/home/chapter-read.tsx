import { useTranslations } from "next-intl";

import { LAMP_IDS, type LampState, type VerdictColor } from "@/lib/analysis";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { LampIcon, WrenchIcon } from "../icons";
import { Gauge } from "../report/gauge";
import { BULB, ICON, STATE } from "../report/lamp-cluster";
import { Bold, Chapter, ChapterHeading, SUBHEADING } from "./guide-parts";

const LEGEND_ORDER: VerdictColor[] = ["green", "orange", "red", "gray"];
const STATE_ORDER: LampState[] = ["on", "danger", "off"];

const VERDICT_BADGE: Record<VerdictColor, string> = {
  green: "border-green text-green",
  orange: "border-warn bg-warn-badge-bg text-warn-text",
  red: "border-red text-red",
  gray: "border-gray text-gray",
};

function VerdictLegend() {
  const t = useTranslations("home.chapters.lire");
  const verdict = useTranslations("verdict");

  return (
    <ul className="mt-[18px] grid grid-cols-[repeat(auto-fit,minmax(min(250px,100%),1fr))] gap-3.5">
      {LEGEND_ORDER.map((color) => (
        <li
          key={color}
          data-verdict-legend={color}
          className="flex flex-col items-start gap-2.5 rounded-[18px] bg-panel px-5 py-[18px]"
        >
          <Gauge color={color} word={verdict(`word.${color}`)} size="small" />
          <span
            className={cn(
              "rounded-full border-[1.5px] px-3 py-[3px] font-condensed text-base font-bold tracking-[0.06em]",
              VERDICT_BADGE[color],
            )}
          >
            {verdict(`word.${color}`)}
          </span>
          <p className="text-base leading-normal">{t(`verdicts.${color}`)}</p>
        </li>
      ))}
    </ul>
  );
}

function LampLegend() {
  const t = useTranslations("home.chapters.lire");
  const lamps = useTranslations("lamps");

  return (
    <div className="mt-[18px] rounded-[22px] bg-cluster-bg px-5 py-6 text-cluster-ink sm:px-[26px]">
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-4">
        {STATE_ORDER.map((state) => (
          <li key={state} data-lamp-state={state} className="flex items-center gap-3.5">
            <span className={cn("flex size-[52px] flex-none items-center justify-center rounded-full", BULB[state])}>
              <LampIcon lamp="internet" className={cn("size-6", ICON[state])} />
            </span>
            <span>
              <strong className={cn("block text-[17px] font-bold", STATE[state])}>{lamps(`state.${state}`)}</strong>
              <span className="block text-[15px] leading-[1.4] text-cluster-ink2">{t(`states.${state}`)}</span>
            </span>
          </li>
        ))}
      </ul>
      <div aria-hidden="true" className="my-[22px] h-px bg-cluster-muted opacity-35" />
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-x-6 gap-y-[18px]">
        {LAMP_IDS.map((lamp) => (
          <li key={lamp} data-lamp-legend={lamp} className="flex items-start gap-3.5">
            <span className={cn("flex size-11 flex-none items-center justify-center rounded-full", BULB.on)}>
              <LampIcon lamp={lamp} className={cn("size-[22px]", ICON.on)} />
            </span>
            <span>
              <strong className="block text-[17px] font-bold text-cluster-ink">
                <EngineText code={`lamp.${lamp}.name`} />
              </strong>
              <span className="block text-[15px] leading-[1.45] text-cluster-ink2">{t(`meanings.${lamp}`)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ChapterRead() {
  const t = useTranslations("home.chapters.lire");

  return (
    <Chapter id="lire">
      <ChapterHeading id="lire" />
      <h3 className={cn(SUBHEADING, "mt-7")}>{t("verdictHeading")}</h3>
      <p className="mt-2 max-w-[66ch] text-lg leading-[1.6] text-ink2">{t("verdictIntro")}</p>
      <VerdictLegend />
      <div className="mt-3.5 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-[18px] bg-panel2 px-[22px] py-[18px] shadow-[inset_0_0_0_1.5px_var(--line)]">
        <WrenchIcon className="size-[34px] flex-none stroke-accent" />
        <p className="min-w-0 flex-[1_1_320px] text-[17px] leading-[1.55]">{t.rich("mechanic", { b: Bold })}</p>
      </div>
      <h3 className={cn(SUBHEADING, "mt-10")}>{t("lampsHeading")}</h3>
      <p className="mt-2 max-w-[66ch] text-lg leading-[1.6] text-ink2">{t("lampsIntro")}</p>
      <LampLegend />
    </Chapter>
  );
}
