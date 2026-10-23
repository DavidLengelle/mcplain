import { useTranslations } from "next-intl";

import type { Alert, AnalysisResult } from "@/lib/analysis";
import { alertsOfColor, firstServer } from "@/lib/report";
import { cn } from "@/lib/utils";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { LampCount, LampPanel } from "../report/lamp-cluster";
import { BADGE, DOT, pointColor } from "../report/point-styles";
import { MessageText, VerdictFrame } from "../report/verdict-block";

export const EXAMPLE_VERDICT_TITLE_ID = "example-verdict-title";
export const EXAMPLE_LAMPS_HEADING_ID = "example-lamps";

function firstAlert(result: AnalysisResult): Alert | null {
  const alerts = result.verdict.alerts;
  return alertsOfColor(alerts, "red")[0] ?? alerts[0] ?? null;
}

function ExampleAlert({ alert }: { alert: Alert }) {
  const points = useTranslations("points");
  const color = pointColor(alert);

  return (
    <div
      data-example-alert={alert.rule}
      className="flex flex-wrap items-center gap-x-[18px] gap-y-2 rounded-[14px] bg-panel px-4 py-3.5"
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
      <span
        className={cn(
          "rounded-full border-[1.5px] px-3 py-[3px] font-condensed text-sm font-semibold tracking-[0.06em]",
          BADGE[color],
        )}
      >
        {points(`badge.${color}`)}
      </span>
    </div>
  );
}

export function ExampleReport({ result }: { result: AnalysisResult }) {
  const t = useTranslations("home.chapters.exemple");
  const server = firstServer(result);
  const verdict = result.verdict;
  const alert = firstAlert(result);
  const name = result.source?.name ?? server?.name ?? null;
  const version = result.source?.version ?? null;

  return (
    <div
      data-example-report=""
      className="mt-5 flex flex-col gap-4 rounded-[26px] bg-panel2 p-3 shadow-[inset_0_0_0_1.5px_var(--line)] sm:p-[22px]"
    >
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm text-muted">
        {name !== null && (
          <span className="text-ink">
            <RawText value={name} limit={160} />
          </span>
        )}
        {version !== null && (
          <>
            <span aria-hidden="true">·</span>
            <RawText value={version} limit={60} />
          </>
        )}
        {(name !== null || version !== null) && <span aria-hidden="true">·</span>}
        <span>{t("demo")}</span>
      </p>
      <VerdictFrame
        color={verdict.color}
        size="compact"
        titleId={EXAMPLE_VERDICT_TITLE_ID}
        title={<MessageText message={verdict.title} />}
      >
        {verdict.summary !== null && (
          <p className="max-w-[60ch] text-[17px] leading-[1.55] text-ink2">
            <MessageText message={verdict.summary} />
          </p>
        )}
      </VerdictFrame>
      {server !== null && (
        <LampPanel
          lamps={server.lamps}
          domains={server.internet_domains}
          headingId={EXAMPLE_LAMPS_HEADING_ID}
          headingAs="h3"
          status={<LampCount lamps={server.lamps} />}
          size="compact"
        />
      )}
      {alert !== null && <ExampleAlert alert={alert} />}
    </div>
  );
}
