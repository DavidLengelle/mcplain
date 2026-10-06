"use client";

import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { AnalysisResult, Lamp, Server } from "@/lib/analysis";
import { joinList, litLamps } from "@/lib/report";

import { EngineText, useEngineString } from "../engine-text";
import { InterfaceText } from "../param-text";

export const PLAIN_HEADING_ID = "plain-heading";

export function useLampActions(): (lamps: Lamp[]) => string | null {
  const engine = useEngineString();
  const locale = useLocale();
  return (lamps: Lamp[]) => {
    const phrases = litLamps(lamps).map((lamp) => engine(`lamp.${lamp.id}.phrase`));
    if (phrases.length === 0) {
      return null;
    }
    return joinList(locale, phrases);
  };
}

function Box({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl bg-panel px-[22px] py-5">
      <p className="font-condensed text-sm font-semibold tracking-[0.1em] text-accent">{label}</p>
      <p className="mt-2 text-lg leading-[1.45]">{children}</p>
    </div>
  );
}

function CanDo({ server }: { server: Server }) {
  const t = useTranslations("plain");
  const actions = useLampActions()(server.lamps);
  if (actions === null) {
    return <>{t("canDoNothing")}</>;
  }
  return <>{t("canDo", { actions })}</>;
}

function distinctRules(result: AnalysisResult): string[] {
  return Array.from(new Set(result.verdict.alerts.map((alert) => alert.rule)));
}

function Found({ result, server }: { result: AnalysisResult; server: Server }) {
  const t = useTranslations("plain");
  const verdict = result.verdict;
  const rules = distinctRules(result);
  if (rules.length > 0) {
    return (
      <>
        <EngineText code={`rule.${rules[0]}.plain_found`} />
        {rules.length > 1 && <> {t("morePoints", { count: rules.length - 1 })}</>}
      </>
    );
  }
  if (verdict.color === "gray" && verdict.title !== null) {
    return <EngineText code={verdict.title.code} params={verdict.title.params} />;
  }
  if (server.internet_domains !== null && server.internet_domains.length > 0) {
    return <InterfaceText code="plain.foundNothingDomains" params={{ domains: server.internet_domains.join(", ") }} />;
  }
  return <>{t("foundNothing")}</>;
}

function Advice({ result }: { result: AnalysisResult }) {
  const t = useTranslations("plain");
  const verdict = result.verdict;
  const rules = distinctRules(result);
  if (rules.length > 0) {
    return <EngineText code={`rule.${rules[0]}.plain_advice`} />;
  }
  if (verdict.color === "gray" && verdict.summary !== null) {
    return <EngineText code={verdict.summary.code} params={verdict.summary.params} />;
  }
  return <>{t("adviceNothing")}</>;
}

export function PlainSummary({ result, server }: { result: AnalysisResult; server: Server }) {
  const t = useTranslations("plain");

  return (
    <section aria-labelledby={PLAIN_HEADING_ID}>
      <h2 id={PLAIN_HEADING_ID} className="mb-3.5 font-condensed text-2xl font-bold tracking-[0.08em]">
        {t("heading")}
      </h2>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-3.5">
        <Box label={t("canDoLabel")}>
          <CanDo server={server} />
        </Box>
        <Box label={t("foundLabel")}>
          <Found result={result} server={server} />
        </Box>
        <Box label={t("adviceLabel")}>
          <Advice result={result} />
        </Box>
      </div>
    </section>
  );
}
