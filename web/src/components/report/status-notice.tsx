import { useTranslations } from "next-intl";

import type { AnalysisResult } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { ReportSection } from "./section";

const MAX_FILES = 20;

export function StatusNotice({ result }: { result: AnalysisResult }) {
  const t = useTranslations("status");
  if (result.status === "ok" && result.notes.length === 0) {
    return null;
  }

  return (
    <ReportSection id="status-heading" title={t("heading")}>
      <div className="flex flex-col gap-2">
        <p className="font-semibold">
          <EngineText code={`status.${result.status}`} params={{ language: result.language ?? "" }} />
        </p>
        {result.error !== null && (
          <p>
            <EngineText code={result.error.code} params={result.error.params} />
          </p>
        )}
        {result.notes.map((note) => (
          <p key={note}>
            <EngineText code={note} />
          </p>
        ))}
        {result.status === "compiled" && result.compiled_files.length > 0 && (
          <ul className="list-disc pl-6">
            {result.compiled_files.slice(0, MAX_FILES).map((path) => (
              <li key={path}>
                <EngineText code="cli.limits.compiled" />
                {": "}
                <RawText value={path} limit={160} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </ReportSection>
  );
}
