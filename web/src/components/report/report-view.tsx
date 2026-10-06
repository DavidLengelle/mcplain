"use client";

import { useState } from "react";

import type { AnalysisResult, AnalysisView, Tool } from "@/lib/analysis";
import { alertsOfTool, defaultToolIndex, firstServer } from "@/lib/report";

import { AiNoticeSlot } from "./ai-notice-slot";
import { AlertPoints } from "./alert-points";
import { BackToTop } from "./back-to-top";
import { CandidatesList } from "./candidates-list";
import { IdentityLine } from "./identity-line";
import { LampCluster } from "./lamp-cluster";
import { LinkListNotice } from "./link-list-notice";
import { PlainSummary } from "./plain-summary";
import { ReportEnd } from "./report-end";
import { TechDetails } from "./tech-details";
import { ToolGrid } from "./tool-grid";
import { ToolSheet } from "./tool-sheet";
import { VerdictBlock } from "./verdict-block";

const LINK_LIST = "link_list";

function toolsOf(result: AnalysisResult): Tool[] {
  const server = firstServer(result);
  if (server === null) {
    return [];
  }
  return server.tools;
}

function FullReport({ analysis, result }: { analysis: AnalysisView; result: AnalysisResult }) {
  const server = firstServer(result);
  const tools = toolsOf(result);
  const alerts = result.verdict.alerts;
  const [selected, setSelected] = useState(() => defaultToolIndex(tools, alerts));
  const [detailsOpen, setDetailsOpen] = useState(false);
  const tool = tools[selected] ?? null;

  return (
    <div className="flex flex-col gap-7" data-report="">
      <IdentityLine analysis={analysis} source={result.source} />
      <VerdictBlock analysis={analysis} result={result} />
      <AiNoticeSlot />
      {server !== null && <PlainSummary result={result} server={server} />}
      {server !== null && <LampCluster server={server} />}
      {(server !== null || alerts.length > 0) && (
        <AlertPoints result={result} tools={tools} onPickTool={setSelected} onOpenDetails={() => setDetailsOpen(true)} />
      )}
      {server !== null && <ToolGrid tools={tools} selected={selected} onPick={setSelected} />}
      {tool !== null && <ToolSheet tool={tool} index={selected} alerts={alertsOfTool(tool, alerts)} />}
      <TechDetails
        analysis={analysis}
        result={result}
        server={server}
        tools={tools}
        open={detailsOpen}
        onToggle={() => setDetailsOpen(!detailsOpen)}
      />
      <ReportEnd analysis={analysis} />
      <BackToTop />
    </div>
  );
}

export function ReportView({ analysis }: { analysis: AnalysisView }) {
  const result = analysis.result;
  if (result === null) {
    return null;
  }
  if (result.status === "multiple_servers") {
    return (
      <div className="flex flex-col gap-7" data-report="">
        <IdentityLine analysis={analysis} source={result.source} />
        <CandidatesList analysis={analysis} result={result} />
        <ReportEnd analysis={analysis} />
      </div>
    );
  }
  if (result.verdict.gray_case === LINK_LIST) {
    return (
      <div className="flex flex-col gap-7" data-report="">
        <IdentityLine analysis={analysis} source={result.source} />
        <LinkListNotice result={result} />
        <ReportEnd analysis={analysis} />
      </div>
    );
  }
  return <FullReport analysis={analysis} result={result} />;
}
