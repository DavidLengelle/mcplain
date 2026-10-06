"use client";

import { useTranslations } from "next-intl";
import { Fragment, type ReactNode } from "react";

import type { AnalysisResult, AnalysisView, Server, Tool } from "@/lib/analysis";
import { DETAILS_ID } from "@/lib/constants";
import { alertPlace, alertsOutsideTools, codeDomains, invisibleCounts, sensitiveMatches } from "@/lib/report";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";

export const DETAILS_HEADING_ID = "details-heading";
export const DETAILS_PANEL_ID = "details-panel";

function Item({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  let classes = "rounded-xl bg-panel2 px-4 py-3.5";
  if (wide) {
    classes = "rounded-xl bg-panel2 px-4 py-3.5 sm:col-span-2";
  }
  return (
    <div className={classes}>
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="mt-1 font-semibold [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

function Chips({ values }: { values: string[] }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {values.map((value) => (
        <span key={value} className="rounded-md bg-code-bg px-2 py-0.5 text-[13px] font-normal text-ink">
          <RawText value={value} limit={160} />
        </span>
      ))}
    </span>
  );
}

function ServerItems({ server }: { server: Server }) {
  const t = useTranslations("details");
  const domains = codeDomains(server);
  const sensitive = sensitiveMatches(server);
  const invisible = invisibleCounts(server);
  const scripts = server.install_scripts;

  return (
    <>
      <Item label={t("domains")}>
        {domains.length === 0 && t("noneFeminine")}
        {domains.length > 0 && <Chips values={domains} />}
      </Item>
      <Item label={t("sensitive")}>
        {sensitive.length === 0 && t("none")}
        {sensitive.length > 0 && <Chips values={sensitive} />}
      </Item>
      <Item label={t("install")}>
        {scripts.length === 0 && t("none")}
        {scripts.length > 0 && (
          <span className="flex flex-col gap-1.5">
            {scripts.map((script, index) => (
              <span key={index} className="font-normal">
                <EngineText code={`install.${script.kind}`} />
                {t("colon")}
                <RawText value={script.command} limit={200} />
              </span>
            ))}
          </span>
        )}
      </Item>
      <Item label={t("invisible")}>
        {invisible.length === 0 && t("none")}
        {invisible.length > 0 && (
          <span className="flex flex-wrap gap-1.5">
            {invisible.map((item) => (
              <span
                key={item.label}
                data-invisible-count={item.label}
                className="rounded-sm border border-warn bg-warn-note px-1.5 font-mono text-[13px] text-warn-text"
              >
                {t("invisibleCount", { label: item.label, count: item.count })}
              </span>
            ))}
          </span>
        )}
      </Item>
    </>
  );
}

function OutsideItem({ result, tools }: { result: AnalysisResult; tools: Tool[] }) {
  const t = useTranslations("details");
  const outside = alertsOutsideTools(result.verdict.alerts, tools);
  if (outside.length === 0) {
    return null;
  }
  return (
    <Item label={t("outside")} wide>
      <ul className="flex flex-col gap-1.5">
        {outside.map((alert, index) => {
          const place = alertPlace(alert);
          return (
            <li key={index} data-outside-alert={alert.rule}>
              <EngineText code={`rule.${alert.rule}.plain_title`} />
              {place !== null && (
                <span className="font-normal text-ink2">
                  {t("colon")}
                  <RawText value={place} limit={200} />
                </span>
              )}
              {place === null && alert.detail !== null && (
                <span className="font-normal text-ink2">
                  {t("colon")}
                  <RawText value={alert.detail} limit={200} />
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Item>
  );
}

function ReputationItem({ result }: { result: AnalysisResult }) {
  const t = useTranslations("details");
  const reputation = result.reputation;
  if (reputation === null) {
    return null;
  }
  const reported = reputation.packages.filter((item) => item.malicious.length > 0);
  return (
    <Item label={t("reputation")}>
      <span className="font-normal">
        {reputation.status === "checked" && <EngineText code="cli.reputation.checked" params={{ count: reputation.queried }} />}
        {reputation.status === "unavailable" && <EngineText code="cli.reputation.unavailable" />}
        {reputation.status === "not_checked" && <EngineText code="cli.reputation.not_checked" />}
      </span>
      {reported.map((item, index) => (
        <span key={index} className="mt-1 block">
          <RawText value={item.name} limit={160} />
          {item.version !== null && (
            <>
              {" "}
              <RawText value={item.version} limit={60} />
            </>
          )}
          {t("colon")}
          {item.malicious.map((report) => report.id).join(", ")}
        </span>
      ))}
    </Item>
  );
}

function SourceItems({ analysis, result }: { analysis: AnalysisView; result: AnalysisResult }) {
  const t = useTranslations("details");
  const source = result.source;

  return (
    <>
      {source !== null && (
        <Item label={t("why")}>
          <span className="font-normal">
            <EngineText code={source.reason} />
          </span>
        </Item>
      )}
      <Item label={t("rules")}>{t("rulesValue", { version: result.verdict.rules_version, count: result.verdict.rules_count })}</Item>
      {result.verdict.reasons.length > 0 && (
        <Item label={t("reasons")} wide>
          <ul className="flex flex-col gap-1 font-normal">
            {result.verdict.reasons.map((reason) => (
              <li key={reason}>
                <EngineText code={`reason.${reason}`} params={{ domains: result.verdict.contacted_domains.join(", ") }} />
              </li>
            ))}
          </ul>
        </Item>
      )}
      {source !== null && (
        <Item label={t("source")} wide>
          <span className="flex flex-col gap-1 font-normal">
            <RawText value={source.url} limit={300} />
            {source.revision !== null && (
              <span>
                {t("revision")}
                {t("colon")}
                <RawText value={source.revision} limit={80} />
              </span>
            )}
            {source.integrity !== null && (
              <span>
                {t("integrity")}
                {t("colon")}
                <RawText value={source.integrity} limit={160} />
              </span>
            )}
          </span>
        </Item>
      )}
      <Item label={t("input")} wide>
        <RawText value={analysis.input} limit={500} />
        {analysis.select !== null && (
          <span className="block font-normal">
            {t("select")}
            {t("colon")}
            <RawText value={analysis.select} limit={500} />
          </span>
        )}
      </Item>
      {result.ignored_arguments.length > 0 && (
        <Item label={t("ignored")} wide>
          {result.ignored_arguments.map((argument, index) => (
            <Fragment key={index}>
              {index > 0 && " "}
              <RawText value={argument} limit={120} />
            </Fragment>
          ))}
        </Item>
      )}
    </>
  );
}

type DetailsProps = {
  analysis: AnalysisView;
  result: AnalysisResult;
  server: Server | null;
  tools: Tool[];
  open: boolean;
  onToggle: () => void;
};

export function TechDetails({ analysis, result, server, tools, open, onToggle }: DetailsProps) {
  const t = useTranslations("details");
  let toggleLabel = t("show");
  if (open) {
    toggleLabel = t("hide");
  }

  return (
    <section
      id={DETAILS_ID}
      aria-labelledby={DETAILS_HEADING_ID}
      className="scroll-mt-[calc(var(--header-height,6rem)+1rem)] rounded-[18px] bg-panel px-5 py-1 sm:px-6"
    >
      <h2 id={DETAILS_HEADING_ID}>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={DETAILS_PANEL_ID}
          onClick={onToggle}
          className="flex min-h-16 w-full cursor-pointer items-center justify-between gap-3 text-left font-condensed text-[22px] font-bold tracking-[0.08em] text-ink"
        >
          <span>{t("heading")}</span>
          <span className="rounded-[10px] border-[1.5px] border-btn-border px-3.5 py-2 font-sans text-sm font-medium tracking-normal">
            {toggleLabel}
          </span>
        </button>
      </h2>
      <dl
        id={DETAILS_PANEL_ID}
        hidden={!open}
        className="mb-5 grid grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-2.5"
      >
        {server !== null && <ServerItems server={server} />}
        <OutsideItem result={result} tools={tools} />
        <ReputationItem result={result} />
        <SourceItems analysis={analysis} result={result} />
      </dl>
    </section>
  );
}

