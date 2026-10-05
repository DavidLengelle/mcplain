import { useTranslations } from "next-intl";

import type { Alert, AnalysisView, Server } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { AiNoticeSlot } from "./ai-notice-slot";
import { AlertList } from "./alert-list";
import { CandidatesList } from "./candidates-list";
import { OutsideSection } from "./outside-section";
import { ReportSection } from "./section";
import { SourceSection } from "./source-section";
import { StatusNotice } from "./status-notice";
import { ToolCard } from "./tool-card";
import { VerdictPanel } from "./verdict-panel";

type Placement = { byTool: Map<string, Alert[]>; others: Alert[] };

function placeAlerts(alerts: Alert[], servers: Server[]): Placement {
  const toolNames = new Set(servers.flatMap((server) => server.tools.map((tool) => tool.name)));
  const byTool = new Map<string, Alert[]>();
  const others: Alert[] = [];
  for (const alert of alerts) {
    if (alert.tool === null || !toolNames.has(alert.tool)) {
      others.push(alert);
      continue;
    }
    const group = byTool.get(alert.tool);
    if (group === undefined) {
      byTool.set(alert.tool, [alert]);
    } else {
      group.push(alert);
    }
  }
  return { byTool, others };
}

type ServerReportProps = { server: Server; position: number; placement: Placement; withOthers: boolean };

function ServerReport({ server, position, placement, withOthers }: ServerReportProps) {
  const t = useTranslations("report");
  let others: Alert[] = [];
  if (withOthers) {
    others = placement.others;
  }

  return (
    <>
      <ReportSection id={`tools-heading-${position}`} title={t("toolsHeading")}>
        {server.tools.length === 0 && <p>{t("noTools")}</p>}
        {server.tools.map((tool, index) => (
          <ToolCard key={index} tool={tool} alerts={placement.byTool.get(tool.name) ?? []} />
        ))}
      </ReportSection>
      <OutsideSection server={server} alerts={others} />
    </>
  );
}

function FailedReport({ analysis }: { analysis: AnalysisView }) {
  const t = useTranslations("grayStates");
  const result = analysis.result;
  if (result === null) {
    return null;
  }

  return (
    <VerdictPanel color="gray">
      <h3 className="text-xl font-bold">{t("failed.title")}</h3>
      {analysis.error_code !== null && (
        <p>
          <EngineText code={`job.${analysis.error_code}`} />
        </p>
      )}
      {result.error !== null && result.error.code !== `job.${analysis.error_code}` && (
        <p>
          <EngineText code={result.error.code} params={result.error.params} />
        </p>
      )}
    </VerdictPanel>
  );
}

export function ReportView({ analysis }: { analysis: AnalysisView }) {
  const t = useTranslations("report");
  const result = analysis.result;
  if (result === null) {
    return null;
  }
  const placement = placeAlerts(result.verdict.alerts, result.servers);
  const finished = (
    <SourceSection
      analysis={analysis}
      source={result.source}
      reputation={result.reputation}
      ignoredArguments={result.ignored_arguments}
      verdict={result.verdict}
    />
  );

  if (analysis.state === "failed") {
    return (
      <div className="flex flex-col gap-10">
        <FailedReport analysis={analysis} />
        {finished}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-10">
      <VerdictPanel
        color={result.verdict.color}
        alertCount={result.verdict.alerts.length}
        reasons={result.verdict.reasons}
        contactedDomains={result.verdict.contacted_domains}
      />
      <AiNoticeSlot />
      <StatusNotice result={result} />
      {result.status === "multiple_servers" && (
        <CandidatesList
          analysis={analysis}
          candidates={result.available_servers}
          truncated={result.available_servers_truncated}
        />
      )}
      {result.servers.map((server, index) => (
        <ServerReport key={index} server={server} position={index} placement={placement} withOthers={index === 0} />
      ))}
      {result.servers.length === 0 && placement.others.length > 0 && (
        <ReportSection id="other-alerts-heading" title={t("otherAlerts")}>
          <AlertList alerts={placement.others} showScope />
        </ReportSection>
      )}
      {finished}
    </div>
  );
}
