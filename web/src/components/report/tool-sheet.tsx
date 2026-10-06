"use client";

import { useTranslations } from "next-intl";
import { Fragment } from "react";

import type { Alert, Tool } from "@/lib/analysis";
import { SHEET_ID } from "@/lib/constants";
import { alertPlace, findingPlaces, litLamps, placeText, toolNumber } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText, useEngineString } from "../engine-text";
import { RawText } from "../raw-text";
import { ToolTitle } from "./tool-grid";

export const SHEET_TITLE_ID = "sheet-title";

function AlertNote({ alert, more }: { alert: Alert; more: number }) {
  const t = useTranslations("sheet");
  const place = alertPlace(alert);
  let frame = "bg-warn-note shadow-[inset_0_0_0_1.5px_var(--warn)]";
  let title = "text-warn-text";
  let why = t("why.orange");
  if (alert.color === "red") {
    frame = "bg-red-note shadow-[inset_0_0_0_1.5px_var(--red)]";
    title = "text-red";
    why = t("why.red");
  }

  return (
    <div role="note" data-sheet-alert={alert.rule} className={cn("mt-[18px] rounded-[14px] px-[18px] py-4", frame)}>
      <strong className={cn("block font-condensed text-lg font-bold tracking-[0.06em]", title)}>{why}</strong>
      <p className="mt-1.5 mb-2.5 text-base leading-normal">
        <EngineText code={`rule.${alert.rule}.plain_found`} />
      </p>
      {alert.quote !== null && alert.quote !== "" && (
        <div className="mb-2.5">
          <span className="mb-1 block text-[13px] text-ink2">{t("quote")}</span>
          <RawText value={alert.quote} variant="block" limit={400} />
        </div>
      )}
      {place !== null && (
        <span className="text-sm text-ink2">
          {t("where")}{" "}
          <code className="rounded-md bg-code-bg px-2 py-0.5 text-[13px] text-ink">
            <RawText value={place} limit={200} />
          </code>
        </span>
      )}
      {more > 0 && <p className="mt-2 text-sm text-ink2">{t("moreAlerts", { count: more })}</p>}
    </div>
  );
}

function Announced({ tool }: { tool: Tool }) {
  const t = useTranslations("sheet");
  const description = tool.description.trim();
  const annotations = Object.entries(tool.annotations);

  return (
    <div className="rounded-2xl bg-panel2 px-[22px] py-5">
      <h4 className="font-condensed text-lg font-bold tracking-[0.08em]">
        {t("announces")} <span className="font-medium text-faint">{t("byAuthor")}</span>
      </h4>
      <span className="mt-2.5 inline-block rounded-full bg-orig-bg px-2.5 py-0.5 text-xs font-semibold text-orig-fg">
        {t("authorText")}
      </span>
      <div className="mt-2.5" data-description="">
        {description === "" && tool.description_is_dynamic && <p className="text-ink2">{t("dynamicDescription")}</p>}
        {description === "" && !tool.description_is_dynamic && <p className="text-ink2">{t("noDescription")}</p>}
        {description !== "" && <RawText value={tool.description} variant="block" limit={800} />}
        {description !== "" && tool.description_is_dynamic && (
          <p className="mt-2 text-sm text-ink2">
            <EngineText code="cli.tool.description_partly_dynamic" />
          </p>
        )}
      </div>
      {(annotations.length > 0 || tool.annotations_are_dynamic) && (
        <p className="mt-3.5 text-[15px] leading-normal text-muted">
          {t("annotations")}{" "}
          {annotations.map(([key, value], index) => (
            <Fragment key={key}>
              {index > 0 && ", "}
              <EngineText code={`annotation.${key}`} />
              {t("colon")}
              <EngineText code={`cli.value.${String(value)}`} />
            </Fragment>
          ))}
          {tool.annotations_are_dynamic && (
            <>
              {annotations.length > 0 && ", "}
              <EngineText code="cli.tool.annotations_dynamic" />
            </>
          )}
        </p>
      )}
      {tool.parameters.length > 0 && (
        <div className="mt-3.5">
          <p className="text-sm text-faint">{t("parameters")}</p>
          <ul className="mt-1 flex flex-col gap-1.5 text-sm">
            {tool.parameters.map((parameter, index) => (
              <li key={index}>
                <span className="font-medium text-ink">
                  <RawText value={parameter.name} limit={100} />
                </span>
                {parameter.description !== null && (
                  <>
                    {t("colon")}
                    <span className="text-ink2">
                      <RawText value={parameter.description} limit={300} />
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CodeCan({ tool }: { tool: Tool }) {
  const t = useTranslations("sheet");
  const state = useTranslations("lamps");
  const engine = useEngineString();
  const lit = litLamps(tool.lamps);
  const { places, more } = findingPlaces(tool);

  return (
    <div className="rounded-2xl bg-panel2 px-[22px] py-5">
      <h4 className="font-condensed text-lg font-bold tracking-[0.08em]">{t("codeCan")}</h4>
      {lit.length === 0 && <p className="mt-3 text-lg leading-snug font-semibold">{t("nothing")}</p>}
      {lit.map((lamp) => (
        <p key={lamp.id} data-can={lamp.id} className="mt-3 text-lg leading-snug font-semibold">
          {t("canAction", { action: engine(`lamp.${lamp.id}.phrase`) })}
          {lamp.state === "danger" && (
            <span className="ml-2 rounded-full border-[1.5px] border-red px-2 py-px font-condensed text-sm tracking-[0.06em] text-red">
              {state("state.danger")}
            </span>
          )}
        </p>
      ))}
      {tool.gaps.length > 0 && (
        <p className="mt-3 text-sm text-ink2">
          {t("incomplete")}{" "}
          {tool.gaps.map((gap, index) => (
            <Fragment key={gap}>
              {index > 0 && ", "}
              <EngineText code={`gap.${gap}`} />
            </Fragment>
          ))}
        </p>
      )}
      <p className="mt-3.5 text-sm text-faint">{t("whereInCode")}</p>
      <p className="mt-1 font-mono text-[13px] leading-relaxed text-ink2 [overflow-wrap:anywhere]">
        {places.length === 0 && <span className="font-sans">{t("nowhere")}</span>}
        {places.map((place, index) => (
          <Fragment key={place}>
            {index > 0 && ", "}
            <RawText value={place} limit={200} />
          </Fragment>
        ))}
        {more > 0 && <span className="font-sans"> {t("morePlaces", { count: more })}</span>}
      </p>
    </div>
  );
}

type SheetProps = { tool: Tool; index: number; alerts: Alert[] };

export function ToolSheet({ tool, index, alerts }: SheetProps) {
  const t = useTranslations("sheet");
  const declared = placeText({ function: null, file: tool.file, line: tool.line });

  return (
    <section
      id={SHEET_ID}
      aria-labelledby={SHEET_TITLE_ID}
      data-sheet={index}
      className="scroll-mt-[calc(var(--header-height,6rem)+1rem)] rounded-[22px] bg-panel px-5 py-7 sm:px-[30px]"
    >
      <p className="font-condensed text-sm font-semibold tracking-[0.14em] text-faint">
        {t("number", { number: toolNumber(index) })}
      </p>
      <h3 id={SHEET_TITLE_ID} className="mt-1.5">
        <ToolTitle tool={tool} size="sheet" />
      </h3>
      <p className="mt-1.5 text-sm text-muted">
        <span className="font-mono">
          <RawText value={tool.name} limit={120} />
        </span>{" "}
        · {t("declaredIn")}{" "}
        <span className="font-mono">
          <RawText value={declared} limit={200} />
        </span>
      </p>
      {alerts.length > 0 && <AlertNote alert={alerts[0]} more={alerts.length - 1} />}
      <div className="mt-[18px] grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] gap-3.5">
        <Announced tool={tool} />
        <CodeCan tool={tool} />
      </div>
    </section>
  );
}
