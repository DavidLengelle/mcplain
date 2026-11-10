"use client";

import { useLocale } from "next-intl";
import { useState } from "react";

import { parseNoticeAnswer, parseTranslationAnswer, translationOfTool, withPlainTitles } from "@/lib/ai-text";
import type { AnalysisResult, AnalysisView, Tool } from "@/lib/analysis";
import { alertsOfTool, defaultToolIndex, firstServer } from "@/lib/report";

import { AiNoticeSlot } from "./ai-notice-slot";
import { AlertPoints } from "./alert-points";
import { BackToTop } from "./back-to-top";
import { CandidatesList } from "./candidates-list";
import { CoverageBlock } from "./coverage-block";
import { IdentityLine } from "./identity-line";
import { LampCluster } from "./lamp-cluster";
import { LinkListNotice } from "./link-list-notice";
import { PlainSummary } from "./plain-summary";
import { ReportEnd } from "./report-end";
import { TechDetails } from "./tech-details";
import { ToolGrid } from "./tool-grid";
import { ToolSheet } from "./tool-sheet";
import { useAiText } from "./use-ai-text";
import { VerdictBlock } from "./verdict-block";

const LINK_LIST = "link_list";
const TRANSLATED_LOCALE = "fr";

function toolsOf(result: AnalysisResult): Tool[] {
  const server = firstServer(result);
  if (server === null) {
    return [];
  }
  return server.tools;
}

function FullReport({ analysis, result }: { analysis: AnalysisView; result: AnalysisResult }) {
  const server = firstServer(result);
  const locale = useLocale();
  const finished = analysis.state === "done";
  const notice = useAiText("notice", analysis.id, locale, finished, parseNoticeAnswer);
  const translation = useAiText(
    "translation",
    analysis.id,
    TRANSLATED_LOCALE,
    finished && locale === TRANSLATED_LOCALE,
    parseTranslationAnswer,
  );
  const tools = withPlainTitles(toolsOf(result), notice.answer);
  const alerts = result.verdict.alerts;
  const [selected, setSelected] = useState(() => defaultToolIndex(tools, alerts));
  const [detailsOpen, setDetailsOpen] = useState(false);
  const tool = tools[selected] ?? null;

  return (
    <div className="flex flex-col gap-7" data-report="">
      <IdentityLine analysis={analysis} source={result.source} />
      <VerdictBlock analysis={analysis} result={result} />
      {result.verdict.coverage !== null && <CoverageBlock coverage={result.verdict.coverage} color={result.verdict.color} />}
      {finished && <AiNoticeSlot answer={notice.answer} waiting={notice.waiting} />}
      {server !== null && <PlainSummary result={result} server={server} />}
      {server !== null && <LampCluster server={server} />}
      {(server !== null || alerts.length > 0) && (
        <AlertPoints result={result} tools={tools} onPickTool={setSelected} onOpenDetails={() => setDetailsOpen(true)} />
      )}
      {server !== null && <ToolGrid tools={tools} selected={selected} onPick={setSelected} />}
      {tool !== null && (
        <ToolSheet
          tool={tool}
          index={selected}
          alerts={alertsOfTool(tool, alerts)}
          translation={translationOfTool(translation.answer, selected, tool.parameters.length)}
        />
      )}
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
