import { useTranslations } from "next-intl";

import type { Alert } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { VerdictBadge } from "../verdict-badge";
import { chainText, Place, placeText } from "./place";
import { Label } from "./section";

const MAX_PLACES_PER_RULE = 5;
const DETAIL_PREFIXES = ["capability.", "hidden.", "install.", "sensitive."];
const DETAIL_SEPARATORS = /[\s,]+/;

function groupByRule(alerts: Alert[]): Alert[][] {
  const groups = new Map<string, Alert[]>();
  for (const alert of alerts) {
    const group = groups.get(alert.rule);
    if (group === undefined) {
      groups.set(alert.rule, [alert]);
    } else {
      group.push(alert);
    }
  }
  return Array.from(groups.values());
}

function AlertScope({ alert }: { alert: Alert }) {
  if (alert.tool !== null) {
    return <EngineText code="cli.alert.tool" params={{ name: alert.tool }} />;
  }
  if (alert.shared_by_tools) {
    return <EngineText code="cli.alert.shared" />;
  }
  if (alert.outside !== null) {
    return (
      <>
        <Label>
          <EngineText code="cli.alert.outside_tools" />
        </Label>
        <EngineText code={`cli.outside.${alert.outside}`} />
      </>
    );
  }
  if (alert.file === null) {
    return <EngineText code="cli.alert.package" />;
  }
  return <EngineText code="cli.alert.outside_tools" />;
}

function AlertDetail({ detail }: { detail: string }) {
  const engine = useTranslations("engine");
  const words = detail.split(DETAIL_SEPARATORS).filter((word) => word !== "");

  return (
    <>
      {words.map((word, index) => {
        const prefix = DETAIL_PREFIXES.find((candidate) => /^\w+$/.test(word) && engine.has(`${candidate}${word}` as never));
        return (
          <span key={index} className="mr-2 inline-block">
            <RawText value={word} limit={120} />
            {prefix !== undefined && (
              <>
                {" ("}
                <EngineText code={`${prefix}${word}`} />
                {")"}
              </>
            )}
          </span>
        );
      })}
    </>
  );
}

function AlertPath({ alert }: { alert: Alert }) {
  const parts = [];
  if (alert.source !== null) {
    parts.push(
      <EngineText key="from" code="cli.alert.from" params={{ place: placeText(alert.source.file, alert.source.line) }} />,
    );
  }
  if (alert.steps.length > 0) {
    parts.push(
      <EngineText key="via" code="cli.alert.via" params={{ chain: chainText(alert.steps.map((step) => step.function)) }} />,
    );
  }
  if (alert.source !== null && alert.file !== null) {
    parts.push(<EngineText key="to" code="cli.alert.to" params={{ place: placeText(alert.file, alert.line) }} />);
  }
  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 && " → "}
          {part}
        </span>
      ))}
    </>
  );
}

function AlertPlace({ alert, showScope }: { alert: Alert; showScope: boolean }) {
  const t = useTranslations("alert");
  const hasPath = alert.source !== null || alert.steps.length > 0;

  return (
    <li className="flex flex-col gap-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
      {showScope && (
        <p className="font-semibold">
          <AlertScope alert={alert} />
        </p>
      )}
      {alert.file !== null && (
        <p>
          <Label>{t("place")}</Label>
          <Place file={alert.file} line={alert.line} />
          {alert.function !== null && (
            <>
              {" "}
              <EngineText code="cli.in_function" params={{ name: alert.function }} />
            </>
          )}
        </p>
      )}
      {hasPath && (
        <p>
          <Label>{t("path")}</Label>
          <AlertPath alert={alert} />
        </p>
      )}
      {alert.detail !== null && (
        <p>
          <Label>{t("detail")}</Label>
          <AlertDetail detail={alert.detail} />
        </p>
      )}
      {alert.quote !== null && (
        <div>
          <p>
            <Label>{t("quote")}</Label>
          </p>
          <RawText value={alert.quote} variant="block" limit={300} />
        </div>
      )}
    </li>
  );
}

export function AlertList({ alerts, showScope = false }: { alerts: Alert[]; showScope?: boolean }) {
  const t = useTranslations("alert");

  return (
    <div className="flex flex-col gap-3">
      {groupByRule(alerts).map((group) => {
        const first = group[0];
        return (
          <article
            key={first.rule}
            data-rule={first.rule}
            className="flex flex-col gap-2 rounded-md border border-foreground/25 p-3"
          >
            <h4 className="flex flex-wrap items-center gap-2 text-base font-bold">
              <VerdictBadge color={first.color} />
              <span className="font-mono">{first.rule}</span>
              <span>
                <EngineText code={`rule.${first.rule}.title`} />
              </span>
            </h4>
            <p>
              <Label>{t("kind")}</Label>
              <EngineText code={`kind.${first.kind}`} />
            </p>
            <p>
              <Label>{t("meaning")}</Label>
              <EngineText code={`rule.${first.rule}.explanation`} />
            </p>
            <ul className="flex flex-col gap-2">
              {group.slice(0, MAX_PLACES_PER_RULE).map((alert, index) => (
                <AlertPlace key={index} alert={alert} showScope={showScope} />
              ))}
            </ul>
            {group.length > MAX_PLACES_PER_RULE && <p>{t("more", { count: group.length - MAX_PLACES_PER_RULE })}</p>}
          </article>
        );
      })}
    </div>
  );
}
