import { useFormatter, useTranslations } from "next-intl";

import type { AnalysisView, Source } from "@/lib/analysis";

import { RawText } from "../raw-text";

const SHORT_REVISION = 7;
const DATE_FORMAT = { day: "numeric", month: "long", year: "numeric" } as const;

function SourceLabel({ source }: { source: Source }) {
  const t = useTranslations("identity");
  if (source.kind === "npm") {
    return <>{t("npm")}</>;
  }
  if (source.kind === "pypi") {
    return <>{t("pypi")}</>;
  }
  return <>{t("github")}</>;
}

function SourceVersion({ source }: { source: Source }) {
  const t = useTranslations("identity");
  if (source.version !== null) {
    return (
      <span>
        {t("version")} <RawText value={source.version} limit={60} />
      </span>
    );
  }
  if (source.revision !== null) {
    return (
      <span>
        {t("revision")} <RawText value={source.revision.slice(0, SHORT_REVISION)} limit={60} />
      </span>
    );
  }
  return null;
}

export function useFormattedDate(): (value: string | null) => string | null {
  const format = useFormatter();
  return (value: string | null) => {
    if (value === null) {
      return null;
    }
    const moment = new Date(value);
    if (Number.isNaN(moment.getTime())) {
      return null;
    }
    return format.dateTime(moment, DATE_FORMAT);
  };
}

function Separator() {
  return <span aria-hidden="true">·</span>;
}

export function IdentityLine({ analysis, source }: { analysis: AnalysisView; source: Source | null }) {
  const t = useTranslations("identity");
  const formatDate = useFormattedDate();
  const date = formatDate(analysis.analyzed_at);

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-1.5 text-sm text-muted">
      <span className="inline-flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {source !== null && (
          <>
            <span className="text-ink">
              <RawText value={source.name} limit={160} />
            </span>
            <Separator />
            {(source.version !== null || source.revision !== null) && (
              <>
                <SourceVersion source={source} />
                <Separator />
              </>
            )}
            <span>
              <SourceLabel source={source} />
            </span>
          </>
        )}
        {source === null && (
          <span className="text-ink">
            <RawText value={analysis.input} limit={160} />
          </span>
        )}
      </span>
      {date !== null && analysis.analyzed_at !== null && (
        <time dateTime={analysis.analyzed_at}>{t("analyzedOn", { date })}</time>
      )}
    </div>
  );
}
