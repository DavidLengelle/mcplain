import { useTranslations } from "next-intl";

import type { AnalysisResult } from "@/lib/analysis";

import { ExampleReport } from "./example-report";
import { Chapter, ChapterHeading } from "./guide-parts";

export function ChapterExample({ report }: { report: AnalysisResult | null }) {
  const t = useTranslations("home.chapters.exemple");

  return (
    <Chapter id="exemple">
      <ChapterHeading id="exemple" badge={t("badge")} />
      <p className="mt-3.5 max-w-[66ch] text-lg leading-[1.6] text-ink2">{t("intro")}</p>
      {report !== null && <ExampleReport result={report} />}
      <p className="mt-3.5 text-base leading-[1.55] text-muted">{t("after")}</p>
    </Chapter>
  );
}
