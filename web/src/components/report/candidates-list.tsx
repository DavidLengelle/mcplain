"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { AnalysisResult, AnalysisView } from "@/lib/analysis";
import { MAX_CANDIDATES } from "@/lib/report";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { StartErrorText } from "../start-error";
import { useAnalysisStart } from "../use-analysis-start";

export const CANDIDATES_HEADING_ID = "candidates-heading";

export function CandidatesList({ analysis, result }: { analysis: AnalysisView; result: AnalysisResult }) {
  const t = useTranslations("candidates");
  const { pending, error, start } = useAnalysisStart();
  const [chosen, setChosen] = useState<string | null>(null);
  const candidates = result.available_servers;
  const title = result.verdict.title;

  function choose(path: string) {
    setChosen(path);
    start(analysis.input, path);
  }

  return (
    <section aria-labelledby={CANDIDATES_HEADING_ID} data-candidates="">
      <h1 id={CANDIDATES_HEADING_ID} className="font-condensed text-[32px] leading-tight font-bold">
        {title !== null && <EngineText code={title.code} params={title.params} />}
      </h1>
      <p className="mt-2 text-lg text-ink2">{t("nothingYet")}</p>
      <ul className="mt-4 rounded-2xl bg-panel p-1.5">
        {candidates.slice(0, MAX_CANDIDATES).map((candidate) => (
          <li key={candidate.path}>
            <button
              type="button"
              disabled={pending}
              aria-busy={chosen === candidate.path}
              onClick={() => choose(candidate.path)}
              className="flex min-h-11 w-full cursor-pointer flex-wrap items-center gap-x-4 gap-y-1 rounded-xl px-4 py-3 text-left text-ink hover:bg-row-hover disabled:cursor-wait"
            >
              <span className="font-mono text-[15px]">
                <RawText value={candidate.path} limit={200} expandable={false} />
              </span>
              {candidate.name !== null && (
                <span className="text-ink2">
                  <RawText value={candidate.name} limit={120} expandable={false} />
                </span>
              )}
              <span className="text-sm text-muted">{t("language", { language: candidate.language })}</span>
            </button>
          </li>
        ))}
      </ul>
      {(result.available_servers_truncated || candidates.length > MAX_CANDIDATES) && (
        <p className="mt-2 text-muted">{t("truncated")}</p>
      )}
      <p aria-live="polite" className="mt-2 font-semibold text-red">
        {error !== null && <StartErrorText error={error} />}
      </p>
    </section>
  );
}
