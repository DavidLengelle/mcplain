import { useTranslations } from "next-intl";

import type { AnalysisView } from "@/lib/analysis";

import { useFormattedDate } from "./identity-line";

export function ReportEnd({ analysis }: { analysis: AnalysisView }) {
  const t = useTranslations("reportEnd");
  const formatDate = useFormattedDate();
  const date = formatDate(analysis.analyzed_at);
  if (date === null) {
    return null;
  }

  return (
    <div className="flex flex-wrap justify-between gap-x-6 gap-y-2 text-sm text-muted">
      <span>{t("readOn", { date })}</span>
      {analysis.from_cache && <span data-from-cache="">{t("fromCache", { date })}</span>}
    </div>
  );
}
