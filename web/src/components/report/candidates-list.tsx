"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useRouter } from "@/i18n/navigation";
import type { AnalysisView, ServerCandidate } from "@/lib/analysis";
import { startAnalysis } from "@/lib/api-client";

import { RawText } from "../raw-text";
import { StartErrorText, type StartError } from "../start-error";
import { ReportSection } from "./section";

export const MAX_CANDIDATES = 50;

type CandidatesListProps = { analysis: AnalysisView; candidates: ServerCandidate[]; truncated: boolean };

export function CandidatesList({ analysis, candidates, truncated }: CandidatesListProps) {
  const t = useTranslations("candidates");
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<StartError | null>(null);

  async function choose(path: string) {
    setPending(path);
    setError(null);
    const outcome = await startAnalysis(analysis.input, path);
    if (outcome.kind === "accepted") {
      router.push(`/analyses/${outcome.id}`);
      return;
    }
    setPending(null);
    setError(outcome);
  }

  return (
    <ReportSection id="candidates-heading" title={t("heading")}>
      <p>{t("intro")}</p>
      <ul className="flex flex-col gap-2">
        {candidates.slice(0, MAX_CANDIDATES).map((candidate) => (
          <li key={candidate.path}>
            <Button
              type="button"
              variant="outline"
              disabled={pending !== null}
              aria-busy={pending === candidate.path}
              onClick={() => choose(candidate.path)}
              className="h-auto w-full justify-start gap-1 py-2 text-left text-base whitespace-normal"
            >
              <span className="flex flex-col items-start gap-0.5">
                <RawText value={candidate.path} limit={200} />
                <span className="text-sm font-normal">
                  {candidate.name !== null && (
                    <>
                      <RawText value={candidate.name} limit={120} />{" "}
                    </>
                  )}
                  ({t("language", { language: candidate.language })})
                </span>
              </span>
            </Button>
          </li>
        ))}
      </ul>
      {(truncated || candidates.length > MAX_CANDIDATES) && <p>{t("truncated")}</p>}
      <p aria-live="polite" className="font-semibold text-destructive">
        {error !== null && <StartErrorText error={error} />}
      </p>
    </ReportSection>
  );
}
