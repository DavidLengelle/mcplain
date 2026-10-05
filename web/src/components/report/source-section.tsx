import { useFormatter, useTranslations } from "next-intl";

import type { AnalysisView, Reputation, Source, Verdict } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";
import { Field, Label, ReportSection } from "./section";

function FinishedAt({ value }: { value: string }) {
  const format = useFormatter();
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return (
    <time dateTime={value}>
      {format.dateTime(date, {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })}
    </time>
  );
}

function packageRole(dependency: boolean): string {
  if (dependency) {
    return "cli.reputation.dependency";
  }
  return "cli.reputation.package";
}

function ReputationText({ reputation }: { reputation: Reputation }) {
  const t = useTranslations("source");
  if (reputation.status === "unavailable") {
    return <EngineText code="cli.reputation.unavailable" />;
  }
  if (reputation.status === "not_checked") {
    return <EngineText code="cli.reputation.not_checked" />;
  }
  return (
    <div className="flex flex-col gap-1">
      <p>
        <EngineText code="cli.reputation.checked" params={{ count: reputation.queried }} />
      </p>
      {reputation.packages.length === 0 && (
        <p>
          <EngineText code="cli.reputation.clean" />
        </p>
      )}
      <ul className="list-disc pl-6">
        {reputation.packages.map((item, index) => (
          <li key={index}>
            <RawText value={[item.name, item.version ?? ""].join(" ").trim()} limit={200} /> (
            <EngineText code={packageRole(item.dependency)} />)
            <ul className="list-disc pl-6">
              {item.malicious.map((report) => (
                <li key={report.id}>
                  <RawText value={report.id} limit={60} />
                  {report.all_versions && ` (${t("allVersions")})`}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourceFields({ source }: { source: Source }) {
  const t = useTranslations("source");
  let integrityLabel = "cli.source.integrity_verified";
  if (source.kind === "github") {
    integrityLabel = "cli.source.integrity_archive";
  }

  return (
    <>
      <Field label={t("kind")}>
        <EngineText code={`source_kind.${source.kind}`} />
      </Field>
      <Field label={t("name")}>
        <RawText value={source.name} limit={200} />
      </Field>
      {source.version !== null && (
        <Field label={t("version")}>
          <RawText value={source.version} limit={100} />
          {source.requested_version !== null && (
            <>
              {" ("}
              <Label>{t("requested")}</Label>
              <RawText value={source.requested_version} limit={100} />
              {")"}
            </>
          )}
        </Field>
      )}
      {source.reference !== null && (
        <Field label={t("reference")}>
          <RawText value={source.reference} limit={200} />
        </Field>
      )}
      {source.revision !== null && (
        <Field label={t("revision")}>
          <RawText value={source.revision} limit={80} />
        </Field>
      )}
      {source.subdir !== null && (
        <Field label={t("folder")}>
          <RawText value={source.subdir} limit={200} />
        </Field>
      )}
      {source.repository !== null && (
        <Field label={t("repository")}>
          <RawText value={source.repository} limit={200} />
        </Field>
      )}
      {source.integrity !== null && (
        <Field label={t("integrity")}>
          <RawText value={source.integrity} limit={200} /> (<EngineText code={integrityLabel} />)
        </Field>
      )}
      <Field label={t("artifact")}>
        <EngineText code={`artifact.${source.artifact}`} />
      </Field>
      <Field label={t("what")}>
        <EngineText code={`origin.${source.origin}`} />
      </Field>
      <Field label={t("why")}>
        <EngineText code={source.reason} />
      </Field>
    </>
  );
}

type SourceSectionProps = {
  analysis: AnalysisView;
  source: Source | null;
  reputation: Reputation | null;
  ignoredArguments: string[];
  verdict: Verdict;
};

export function SourceSection({ analysis, source, reputation, ignoredArguments, verdict }: SourceSectionProps) {
  const t = useTranslations("source");

  return (
    <ReportSection id="source-heading" title={t("heading")}>
      <dl className="flex flex-col gap-3">
        {analysis.input !== "" && (
          <Field label={t("input")}>
            <RawText value={analysis.input} limit={500} />
          </Field>
        )}
        {ignoredArguments.length > 0 && (
          <Field label={t("ignored")}>
            <RawText value={ignoredArguments.join(" ")} limit={300} />
          </Field>
        )}
        {source !== null && <SourceFields source={source} />}
        {analysis.finished_at !== null && (
          <Field label={t("date")}>
            <FinishedAt value={analysis.finished_at} />
          </Field>
        )}
        <Field label={t("rules")}>
          {t("rulesValue", { version: verdict.rules_version, count: verdict.rules_count })}
        </Field>
        {reputation !== null && (
          <Field label={t("reputation")}>
            <ReputationText reputation={reputation} />
          </Field>
        )}
      </dl>
    </ReportSection>
  );
}
