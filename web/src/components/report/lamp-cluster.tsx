import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { Lamp, LampState, Server } from "@/lib/analysis";
import { countLamps } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { LampIcon } from "../icons";

export const LAMPS_HEADING_ID = "lamps-heading";

export const BULB: Record<LampState, string> = {
  on: "bg-lamp-on-bg shadow-lamp-on",
  off: "bg-lamp-off-bg shadow-lamp-off",
  danger: "bg-lamp-danger-bg shadow-lamp-danger",
};

export const ICON: Record<LampState, string> = {
  on: "stroke-lamp-on-stroke",
  off: "stroke-lamp-off-stroke",
  danger: "stroke-lamp-danger-stroke",
};

const NAME: Record<LampState, string> = {
  on: "text-cluster-ink",
  off: "text-cluster-ink2",
  danger: "text-cluster-ink",
};

export const STATE: Record<LampState, string> = {
  on: "text-lamp-on-text",
  off: "text-lamp-off-text",
  danger: "text-lamp-danger-text",
};

function LampNote({ lamp, domains }: { lamp: Lamp; domains: string[] | null }) {
  if (lamp.state === "danger" && lamp.rules.length > 0) {
    return <EngineText code={`rule.${lamp.rules[0]}.plain_title`} />;
  }
  if (lamp.note !== null) {
    return <EngineText code={lamp.note} />;
  }
  if (lamp.id === "internet" && lamp.state === "on" && domains !== null) {
    return <EngineText code="lamp.internet.note_domains" params={{ domains: domains.join(", ") }} />;
  }
  return null;
}

function hasNote(lamp: Lamp, domains: string[] | null): boolean {
  if (lamp.state === "danger" && lamp.rules.length > 0) {
    return true;
  }
  if (lamp.note !== null) {
    return true;
  }
  return lamp.id === "internet" && lamp.state === "on" && domains !== null;
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

export type LampPanelSize = "full" | "compact" | "hero";

const PANEL: Record<LampPanelSize, string> = {
  full: "px-5 py-6 sm:px-7",
  compact: "px-5 py-5 sm:px-[22px]",
  hero: "px-5 py-[22px] sm:px-6",
};

const HEADING: Record<LampPanelSize, string> = {
  full: "text-2xl",
  compact: "text-xl",
  hero: "text-xl",
};

const STATUS: Record<LampPanelSize, string> = {
  full: "text-[15px]",
  compact: "text-sm",
  hero: "text-sm",
};

const GRID: Record<LampPanelSize, string> = {
  full: "mt-[22px] mb-1 grid-cols-[repeat(auto-fit,minmax(min(100%,140px),1fr))] gap-x-3 gap-y-[18px]",
  compact: "mt-[18px] mb-0.5 grid-cols-[repeat(auto-fit,minmax(min(100%,120px),1fr))] gap-x-2.5 gap-y-4",
  hero: "mt-5 mb-[18px] grid-cols-3 gap-x-2 gap-y-[18px]",
};

const ITEM: Record<LampPanelSize, string> = {
  full: "gap-2.5",
  compact: "gap-2",
  hero: "gap-2",
};

const BULB_SIZE: Record<LampPanelSize, string> = {
  full: "size-[60px]",
  compact: "size-12",
  hero: "size-[52px]",
};

const ICON_SIZE: Record<LampPanelSize, string> = {
  full: "size-7",
  compact: "size-[22px]",
  hero: "size-6",
};

const LAMP_NAME: Record<LampPanelSize, string> = {
  full: "text-base",
  compact: "text-sm leading-[1.25]",
  hero: "text-sm leading-[1.25]",
};

type HeadingTag = "h2" | "h3" | "p";

function PanelHeading({ as, id, className, children }: { as: HeadingTag; id: string; className: string; children: ReactNode }) {
  if (as === "h3") {
    return (
      <h3 id={id} className={className}>
        {children}
      </h3>
    );
  }
  if (as === "p") {
    return (
      <p id={id} className={className}>
        {children}
      </p>
    );
  }
  return (
    <h2 id={id} className={className}>
      {children}
    </h2>
  );
}

type LampPanelProps = {
  lamps: Lamp[];
  domains: string[] | null;
  headingId: string;
  headingAs: HeadingTag;
  status: ReactNode;
  size: LampPanelSize;
  className?: string;
  children?: ReactNode;
};

export function LampPanel({ lamps, domains, headingId, headingAs, status, size, className, children }: LampPanelProps) {
  const t = useTranslations("lamps");

  return (
    <section
      aria-labelledby={headingId}
      data-lamp-panel={size}
      className={cn("rounded-[22px] bg-cluster-bg text-cluster-ink", PANEL[size], className)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <PanelHeading
          as={headingAs}
          id={headingId}
          className={cn("font-condensed font-bold tracking-[0.08em] text-cluster-ink", HEADING[size])}
        >
          {t("heading")}
        </PanelHeading>
        <span className={cn("text-cluster-muted", STATUS[size])}>{status}</span>
      </div>
      <ul className={cn("grid", GRID[size])}>
        {lamps.map((lamp) => (
          <li
            key={lamp.id}
            data-lamp={lamp.id}
            data-state={lamp.state}
            className={cn("flex flex-col items-center text-center", ITEM[size])}
          >
            <span className={cn("flex items-center justify-center rounded-full", BULB_SIZE[size], BULB[lamp.state])}>
              <LampIcon lamp={lamp.id} className={cn(ICON_SIZE[size], ICON[lamp.state])} />
            </span>
            <span>
              <strong className={cn("block font-semibold", LAMP_NAME[size], NAME[lamp.state])}>
                <EngineText code={`lamp.${lamp.id}.name`} />
              </strong>
              <span
                className={cn("text-[13px] font-semibold", STATE[lamp.state], size === "hero" && "sr-only")}
              >
                {t(`state.${lamp.state}`)}
              </span>
              {hasNote(lamp, domains) && (
                <span
                  className={cn(
                    "mx-auto mt-1 block text-xs leading-[1.35] text-cluster-muted",
                    size === "full" && "max-w-[170px]",
                    size !== "full" && "max-w-[160px]",
                  )}
                >
                  <LampNote lamp={lamp} domains={domains} />
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {children}
    </section>
  );
}

export function LampCluster({ server }: { server: Server }) {
  return (
    <LampPanel
      lamps={server.lamps}
      domains={server.internet_domains}
      headingId={LAMPS_HEADING_ID}
      headingAs="h2"
      status={<LampCount lamps={server.lamps} />}
      size="full"
    />
  );
}
