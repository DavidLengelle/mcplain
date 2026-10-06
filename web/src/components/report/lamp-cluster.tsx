import { useTranslations } from "next-intl";

import type { Lamp, LampState, Server } from "@/lib/analysis";
import { countLamps } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { LampIcon } from "../icons";

export const LAMPS_HEADING_ID = "lamps-heading";

const BULB: Record<LampState, string> = {
  on: "bg-lamp-on-bg shadow-lamp-on",
  off: "bg-lamp-off-bg shadow-lamp-off",
  danger: "bg-lamp-danger-bg shadow-lamp-danger",
};

const ICON: Record<LampState, string> = {
  on: "stroke-lamp-on-stroke",
  off: "stroke-lamp-off-stroke",
  danger: "stroke-lamp-danger-stroke",
};

const NAME: Record<LampState, string> = {
  on: "text-cluster-ink",
  off: "text-cluster-ink2",
  danger: "text-cluster-ink",
};

const STATE: Record<LampState, string> = {
  on: "text-lamp-on-text",
  off: "text-lamp-off-text",
  danger: "text-lamp-danger-text",
};

function LampNote({ lamp, server }: { lamp: Lamp; server: Server }) {
  if (lamp.state === "danger" && lamp.rules.length > 0) {
    return <EngineText code={`rule.${lamp.rules[0]}.plain_title`} />;
  }
  if (lamp.id === "internet" && lamp.state === "on" && server.internet_domains !== null) {
    return <EngineText code="lamp.internet.note_domains" params={{ domains: server.internet_domains.join(", ") }} />;
  }
  return null;
}

function hasNote(lamp: Lamp, server: Server): boolean {
  if (lamp.state === "danger" && lamp.rules.length > 0) {
    return true;
  }
  return lamp.id === "internet" && lamp.state === "on" && server.internet_domains !== null;
}

export function LampCount({ lamps }: { lamps: Lamp[] }) {
  const t = useTranslations("lamps");
  const count = countLamps(lamps);

  return (
    <>
      {t("count", { lit: count.lit, total: count.total })}
      {count.danger > 0 && t("countDanger", { danger: count.danger })}
    </>
  );
}

export function LampCluster({ server }: { server: Server }) {
  const t = useTranslations("lamps");

  return (
    <section
      aria-labelledby={LAMPS_HEADING_ID}
      className="rounded-[22px] bg-cluster-bg px-5 py-6 text-cluster-ink sm:px-7"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={LAMPS_HEADING_ID} className="font-condensed text-2xl font-bold tracking-[0.08em] text-cluster-ink">
          {t("heading")}
        </h2>
        <span className="text-[15px] text-cluster-muted">
          <LampCount lamps={server.lamps} />
        </span>
      </div>
      <ul className="mt-[22px] mb-1 grid grid-cols-[repeat(auto-fit,minmax(min(100%,140px),1fr))] gap-x-3 gap-y-[18px]">
        {server.lamps.map((lamp) => (
          <li
            key={lamp.id}
            data-lamp={lamp.id}
            data-state={lamp.state}
            className="flex flex-col items-center gap-2.5 text-center"
          >
            <span className={cn("flex size-[60px] items-center justify-center rounded-full", BULB[lamp.state])}>
              <LampIcon lamp={lamp.id} className={cn("size-7", ICON[lamp.state])} />
            </span>
            <span>
              <strong className={cn("block text-base font-semibold", NAME[lamp.state])}>
                <EngineText code={`lamp.${lamp.id}.name`} />
              </strong>
              <span className={cn("text-[13px] font-semibold", STATE[lamp.state])}>{t(`state.${lamp.state}`)}</span>
              {hasNote(lamp, server) && (
                <span className="mx-auto mt-1 block max-w-[170px] text-xs leading-[1.35] text-cluster-muted">
                  <LampNote lamp={lamp} server={server} />
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
