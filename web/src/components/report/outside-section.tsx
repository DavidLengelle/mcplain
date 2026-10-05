import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { OUTSIDE_KINDS, type Alert, type DomainRef, type Finding, type Server } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { AlertList } from "./alert-list";
import { Place } from "./place";
import { Label, ReportSection } from "./section";
import { Capabilities } from "./tool-card";

const SERVER_CODE = "server_code";
const MAX_ITEMS = 20;

function Subsection({ title, empty, children }: { title: ReactNode; empty: boolean; children: ReactNode }) {
  const t = useTranslations("outside");

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-lg font-bold">{title}</h3>
      {empty && <p>{t("none")}</p>}
      {!empty && children}
    </section>
  );
}

function More({ total }: { total: number }) {
  const t = useTranslations("outside");
  if (total <= MAX_ITEMS) {
    return null;
  }
  return <p>{t("more", { count: total - MAX_ITEMS })}</p>;
}

function groupByDomain(domains: DomainRef[]): [string, DomainRef[]][] {
  const groups = new Map<string, DomainRef[]>();
  for (const item of domains) {
    const group = groups.get(item.domain);
    if (group === undefined) {
      groups.set(item.domain, [item]);
    } else {
      group.push(item);
    }
  }
  return Array.from(groups.entries()).sort(([first], [second]) => first.localeCompare(second));
}

function OutsideCapabilities({ findings }: { findings: Finding[] }) {
  const shared = findings.filter((finding) => finding.shared_by_tools);
  const outside = findings.filter((finding) => !finding.shared_by_tools);

  return (
    <div className="flex flex-col gap-3">
      <p>
        <EngineText code="cli.outside.counted" />
      </p>
      {shared.length > 0 && (
        <div>
          <p className="font-semibold">
            <EngineText code="cli.shared.heading" />
          </p>
          <Capabilities findings={shared} />
        </div>
      )}
      {OUTSIDE_KINDS.map((kind) => {
        const group = outside.filter((finding) => (finding.outside ?? "never_called") === kind);
        if (group.length === 0) {
          return null;
        }
        return (
          <div key={kind}>
            <p className="font-semibold">
              <EngineText code={`cli.outside.${kind}`} />
            </p>
            <Capabilities findings={group} />
          </div>
        );
      })}
    </div>
  );
}

function CitedUrls({ domains }: { domains: DomainRef[] }) {
  const t = useTranslations("outside");
  const groups = groupByDomain(domains);

  return (
    <>
      <p className="text-sm">{t("urlsHint")}</p>
      <ul className="flex list-disc flex-col gap-1 pl-6">
        {groups.slice(0, MAX_ITEMS).map(([domain, places]) => (
          <li key={domain}>
            <RawText value={domain} limit={120} /> (<EngineText code="cli.places" params={{ count: places.length }} />)
            <br />
            <RawText value={places[0].url} limit={200} /> <Place file={places[0].file} line={places[0].line} />
          </li>
        ))}
      </ul>
      <More total={groups.length} />
    </>
  );
}

export function OutsideSection({ server, alerts }: { server: Server; alerts: Alert[] }) {
  const t = useTranslations("outside");
  const report = useTranslations("report");
  const findings = server.findings.filter((finding) => finding.location_kind === SERVER_CODE);
  const domains = server.domains.filter((item) => item.location_kind === SERVER_CODE);
  const notCountedDomains = server.domains.length - domains.length;

  return (
    <ReportSection id="outside-heading" title={t("heading")}>
      <Subsection title={t("capabilities")} empty={findings.length === 0}>
        <OutsideCapabilities findings={findings} />
      </Subsection>
      <Subsection title={t("urls")} empty={domains.length === 0}>
        <CitedUrls domains={domains} />
      </Subsection>
      {notCountedDomains > 0 && (
        <p className="text-sm">
          <EngineText code="cli.domains.not_counted" params={{ count: notCountedDomains }} />
        </p>
      )}
      <Subsection title={t("sensitive")} empty={server.sensitive_paths.length === 0}>
        <ul className="flex list-disc flex-col gap-1 pl-6">
          {server.sensitive_paths.slice(0, MAX_ITEMS).map((item, index) => (
            <li key={index}>
              <Label>
                <EngineText code={`sensitive.${item.category}`} />
              </Label>
              <RawText value={item.match} limit={200} /> <Place file={item.file} line={item.line} />
            </li>
          ))}
        </ul>
        <More total={server.sensitive_paths.length} />
      </Subsection>
      <Subsection title={t("install")} empty={server.install_scripts.length === 0}>
        <ul className="flex flex-col gap-2">
          {server.install_scripts.slice(0, MAX_ITEMS).map((script, index) => (
            <li key={index} className="flex flex-col gap-1">
              <p>
                <Label>
                  <EngineText code={`install.${script.kind}`} />
                </Label>
                <Place file={script.file} line={script.line} />
              </p>
              <RawText value={script.command} variant="block" limit={300} />
            </li>
          ))}
        </ul>
        <More total={server.install_scripts.length} />
      </Subsection>
      <Subsection title={t("invisible")} empty={server.invisible_unicode.length === 0}>
        <ul className="flex list-disc flex-col gap-1 pl-6">
          {server.invisible_unicode.slice(0, MAX_ITEMS).map((item, index) => (
            <li key={index}>
              <Label>
                <EngineText code={`invisible.${item.category}`} />
              </Label>
              <RawText value={item.codepoints.slice(0, 8).join(" ")} limit={120} />{" "}
              <Place file={item.file} line={item.line} />
              {item.tool !== null && (
                <>
                  {" "}
                  <EngineText code="cli.in_tool" params={{ name: item.tool }} />
                </>
              )}
              {item.hidden_text !== null && (
                <>
                  {" "}
                  <Label>{t("hiddenText")}</Label>
                  <RawText value={item.hidden_text} limit={200} />
                </>
              )}
            </li>
          ))}
        </ul>
        <More total={server.invisible_unicode.length} />
      </Subsection>
      {alerts.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-lg font-bold">{report("otherAlerts")}</h3>
          <AlertList alerts={alerts} showScope />
        </section>
      )}
    </ReportSection>
  );
}
