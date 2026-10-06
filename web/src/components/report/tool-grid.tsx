"use client";

import { useTranslations } from "next-intl";

import type { Lamp, Tool, ToolLevel } from "@/lib/analysis";
import { SHEET_ID } from "@/lib/constants";
import { litLamps, toolNumber } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { useLampActions } from "./plain-summary";

export const TOOLS_HEADING_ID = "tools-heading";

const RING: Record<ToolLevel, string> = {
  none: "",
  warn: "shadow-warn-ring",
  danger: "shadow-red-ring",
};

export function LevelMark({ level }: { level: ToolLevel }) {
  const t = useTranslations("tools");
  if (level === "none") {
    return null;
  }
  let dot = "bg-warn shadow-[0_0_8px_var(--warn-glow)]";
  let text = "text-warn-text";
  if (level === "danger") {
    dot = "bg-red shadow-[0_0_8px_var(--red-glow)]";
    text = "text-red";
  }
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[13px] font-semibold", text)}>
      <span aria-hidden="true" className={cn("size-2 rounded-full", dot)} />
      {t(`level.${level}`)}
    </span>
  );
}

export function ToolSentence({ tool }: { tool: Tool }) {
  const t = useTranslations("tools");
  const actions = useLampActions()(tool.lamps);
  if (tool.plain_sentence !== null) {
    return <RawText value={tool.plain_sentence} limit={300} expandable={false} className="font-sans" />;
  }
  if (actions === null) {
    return <>{t("noLamp")}</>;
  }
  return <>{t("canDo", { actions })}</>;
}

export function LampChips({ lamps }: { lamps: Lamp[] }) {
  const lit = litLamps(lamps);
  if (lit.length === 0) {
    return null;
  }
  return (
    <span className="mt-2 flex flex-wrap gap-x-3.5 gap-y-1.5 text-[13px] text-chip-label">
      {lit.map((lamp) => {
        let dot = "bg-chip-on-dot shadow-chip-on";
        let label = "text-chip-label";
        if (lamp.state === "danger") {
          dot = "bg-chip-danger-dot shadow-chip-danger";
          label = "text-chip-danger";
        }
        return (
          <span key={lamp.id} data-chip={lamp.id} data-state={lamp.state} className={cn("inline-flex items-center gap-[7px] font-medium", label)}>
            <span aria-hidden="true" className="inline-flex size-4 flex-none items-center justify-center rounded-full bg-chip-house">
              <span className={cn("size-2 rounded-full", dot)} />
            </span>
            <EngineText code={`lamp.${lamp.id}.name`} />
          </span>
        );
      })}
    </span>
  );
}

export function ToolTitle({ tool, size }: { tool: Tool; size: "card" | "sheet" }) {
  const t = useTranslations("tools");
  if (tool.plain_title !== null) {
    let classes = "font-condensed text-[25px] leading-[1.1] font-bold";
    if (size === "sheet") {
      classes = "font-condensed text-4xl leading-[1.1] font-bold";
    }
    return (
      <span className="flex flex-col items-start gap-1">
        <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-on-accent">{t("automatic")}</span>
        <RawText value={tool.plain_title} limit={120} expandable={false} className={classes} />
      </span>
    );
  }
  let classes = "text-xl leading-tight font-medium";
  if (size === "sheet") {
    classes = "text-[28px] leading-tight font-medium";
  }
  return <RawText value={tool.name} limit={120} expandable={false} className={classes} />;
}

type CardProps = { tool: Tool; index: number; selected: boolean; onPick: (index: number) => void };

function ToolCard({ tool, index, selected, onPick }: CardProps) {
  const t = useTranslations("tools");
  let ring = RING[tool.level];
  if (selected) {
    ring = "shadow-sel-ring";
  }

  return (
    <a
      href={`#${SHEET_ID}`}
      onClick={() => onPick(index)}
      aria-current={selected}
      data-tool-card={index}
      data-level={tool.level}
      className={cn(
        "flex flex-col gap-1.5 rounded-2xl bg-panel px-[18px] pt-[18px] pb-4 text-left text-ink no-underline transition duration-150 hover:-translate-y-0.5 hover:bg-card-hover motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        ring,
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-condensed text-[13px] font-semibold tracking-[0.12em] text-muted">
          {t("number", { number: toolNumber(index) })}
        </span>
        <LevelMark level={tool.level} />
      </span>
      <span className="mt-1">
        <ToolTitle tool={tool} size="card" />
      </span>
      {tool.plain_title !== null && (
        <span className="font-mono text-[13px] text-muted">
          <RawText value={tool.name} limit={120} expandable={false} />
        </span>
      )}
      <span className="text-[15px] leading-[1.45] text-ink2">
        <ToolSentence tool={tool} />
      </span>
      <LampChips lamps={tool.lamps} />
    </a>
  );
}

type GridProps = { tools: Tool[]; selected: number; onPick: (index: number) => void };

export function ToolGrid({ tools, selected, onPick }: GridProps) {
  const t = useTranslations("tools");

  return (
    <section aria-labelledby={TOOLS_HEADING_ID}>
      <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={TOOLS_HEADING_ID} className="font-condensed text-2xl font-bold tracking-[0.08em]">
          {t("heading", { count: tools.length })}
        </h2>
        {tools.length > 0 && <span className="text-[15px] text-muted">{t("hint")}</span>}
      </div>
      {tools.length === 0 && <p className="rounded-2xl bg-panel px-5 py-[18px] text-[17px]">{t("none")}</p>}
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map((tool, index) => (
          <ToolCard key={index} tool={tool} index={index} selected={index === selected} onPick={onPick} />
        ))}
      </div>
    </section>
  );
}
