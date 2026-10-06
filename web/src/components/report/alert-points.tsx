"use client";

import { useTranslations } from "next-intl";

import type { Alert, AnalysisResult, Tool } from "@/lib/analysis";
import { DETAILS_ID, SHEET_ID } from "@/lib/constants";
import { alertPlace, alertsOfColor, toolIndexOf } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { CheckCircleIcon } from "../icons";
import { RawText } from "../raw-text";

type PointColor = "red" | "orange";

const DOT: Record<PointColor, string> = {
  red: "bg-red shadow-[0_0_10px_var(--red-glow)]",
  orange: "bg-warn shadow-[0_0_10px_var(--warn-glow)]",
};

const BADGE: Record<PointColor, string> = {
  red: "border-red bg-transparent text-red",
  orange: "border-warn bg-warn-badge-bg text-warn-text",
};

function pointColor(alert: Alert): PointColor {
  if (alert.color === "red") {
    return "red";
  }
  return "orange";
}

type PointsProps = {
  result: AnalysisResult;
  tools: Tool[];
  onPickTool: (index: number) => void;
  onOpenDetails: () => void;
};

function PointRow({ alert, tools, onPickTool, onOpenDetails }: { alert: Alert } & Omit<PointsProps, "result">) {
  const t = useTranslations("points");
  const color = pointColor(alert);
  const index = toolIndexOf(tools, alert.tool);
  const place = alertPlace(alert);
  let target = DETAILS_ID;
  if (index !== null) {
    target = SHEET_ID;
  }

  function pick() {
    if (index !== null) {
      onPickTool(index);
    } else {
      onOpenDetails();
    }
  }

  return (
    <li>
      <a
        href={`#${target}`}
        onClick={pick}
        data-point={alert.rule}
        className="flex flex-wrap items-center gap-x-[18px] gap-y-2 rounded-xl px-4 py-3.5 text-ink no-underline hover:bg-row-hover"
      >
        <span aria-hidden="true" className={cn("size-3 flex-none rounded-full", DOT[color])} />
        <span className="min-w-0 flex-[1_1_260px]">
          <strong className="block text-lg font-semibold">
            <EngineText code={`rule.${alert.rule}.plain_title`} />
          </strong>
          <span className="mt-0.5 block text-[15px] text-ink2">
            <EngineText code={`rule.${alert.rule}.plain_found`} />
          </span>
        </span>
        {place !== null && (
          <span className="min-w-0 font-mono text-[13px] text-muted">
            <RawText value={place} limit={120} expandable={false} />
          </span>
        )}
        <span
          className={cn(
            "rounded-full border-[1.5px] px-3 py-[3px] font-condensed text-sm font-semibold tracking-[0.06em]",
            BADGE[color],
          )}
        >
          {t(`badge.${color}`)}
        </span>
      </a>
    </li>
  );
}

function PointGroup({ color, alerts, ...rest }: { color: PointColor; alerts: Alert[] } & Omit<PointsProps, "result">) {
  const t = useTranslations("points");
  const headingId = `points-${color}`;

  return (
    <section aria-labelledby={headingId} data-points={color}>
      <h2 id={headingId} className="font-condensed text-2xl font-bold tracking-[0.08em]">
        {t(`heading.${color}`, { count: alerts.length })}
      </h2>
      <p className="mt-1.5 mb-3.5 text-base text-muted">{t(`intro.${color}`, { count: alerts.length })}</p>
      <ol className="rounded-2xl bg-panel p-1.5">
        {alerts.map((alert, index) => (
          <PointRow key={index} alert={alert} {...rest} />
        ))}
      </ol>
    </section>
  );
}

export function AlertPoints({ result, tools, onPickTool, onOpenDetails }: PointsProps) {
  const t = useTranslations("points");
  const alerts = result.verdict.alerts;
  const red = alertsOfColor(alerts, "red");
  const orange = alertsOfColor(alerts, "orange");
  let empty = t("emptyGreen");
  if (result.verdict.color === "gray") {
    empty = t("emptyGray");
  }

  if (alerts.length === 0) {
    return (
      <section aria-labelledby="points-orange" data-points="none">
        <h2 id="points-orange" className="font-condensed text-2xl font-bold tracking-[0.08em]">
          {t("heading.orange", { count: 0 })}
        </h2>
        <div className="mt-3.5 flex items-center gap-3.5 rounded-2xl bg-panel px-5 py-[18px]">
          <CheckCircleIcon className="size-7 flex-none stroke-green" />
          <p className="text-[17px] leading-normal">{empty}</p>
        </div>
      </section>
    );
  }

  return (
    <>
      {red.length > 0 && (
        <PointGroup color="red" alerts={red} tools={tools} onPickTool={onPickTool} onOpenDetails={onOpenDetails} />
      )}
      {orange.length > 0 && (
        <PointGroup color="orange" alerts={orange} tools={tools} onPickTool={onPickTool} onOpenDetails={onOpenDetails} />
      )}
    </>
  );
}
