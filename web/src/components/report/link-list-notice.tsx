import { useTranslations } from "next-intl";

import type { AnalysisResult } from "@/lib/analysis";

import { EngineText } from "../engine-text";

export const LINK_LIST_HEADING_ID = "link-list-heading";

export function LinkListNotice({ result }: { result: AnalysisResult }) {
  const t = useTranslations("report");
  const { title, summary } = result.verdict;

  return (
    <section
      aria-labelledby={LINK_LIST_HEADING_ID}
      data-link-list=""
      className="rounded-[22px] bg-panel px-6 py-7 sm:px-8"
    >
      <h1 id={LINK_LIST_HEADING_ID} className="font-condensed text-[32px] leading-tight font-bold">
        {title !== null && <EngineText code={title.code} params={title.params} />}
      </h1>
      {summary !== null && (
        <p className="mt-2 text-lg text-ink2">
          <EngineText code={summary.code} params={summary.params} />
        </p>
      )}
      <p className="mt-3 text-muted">{t("pasteAbove")}</p>
    </section>
  );
}
