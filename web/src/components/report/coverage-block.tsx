import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { Coverage, CoverageItem } from "@/lib/analysis";

import { EngineText } from "../engine-text";
import { RawText } from "../raw-text";

export const COVERAGE_HEADING_ID = "coverage-heading";

function placeOf(item: CoverageItem): string | null {
  if (item.file === null) {
    return null;
  }
  if (item.line === null) {
    return item.file;
  }
  return `${item.file}:${item.line}`;
}

function Panel({ label, testId, children }: { label: string; testId: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl bg-panel px-[22px] py-5" data-coverage-part={testId}>
      <p className="font-condensed text-sm font-semibold tracking-[0.1em] text-accent">{label}</p>
      {children}
    </div>
  );
}

function NotCheckedItem({ item }: { item: CoverageItem }) {
  const place = placeOf(item);

  return (
    <li className="border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0" data-coverage-item={item.kind}>
      <p className="text-base leading-normal">
        <strong className="font-semibold">
          <EngineText code={`coverage.kind.${item.kind}`} />
        </strong>
        {item.name !== null && (
          <>
            {" "}
            <span className="font-mono text-[15px] [overflow-wrap:anywhere]">
              <RawText value={item.name} limit={120} />
            </span>
          </>
        )}
      </p>
      <p className="mt-0.5 text-base leading-normal text-ink2">
        <EngineText code={`coverage.reason.${item.reason}`} />
      </p>
      {place !== null && (
        <code className="mt-1.5 inline-block max-w-full rounded-md bg-code-bg px-2 py-0.5 text-[13px] text-ink [overflow-wrap:anywhere]">
          <RawText value={place} limit={200} />
        </code>
      )}
      {item.snippet !== null && item.snippet !== "" && (
        <div className="mt-1.5">
          <RawText value={item.snippet} variant="block" limit={200} />
        </div>
      )}
    </li>
  );
}

export function CoverageBlock({ coverage }: { coverage: Coverage }) {
  const t = useTranslations("coverage");
  const more = coverage.not_checked_count - coverage.not_checked.length;
  const counts = {
    followed: String(coverage.tools_followed),
    total: String(coverage.tools_total),
    read: String(coverage.files_read),
    files: String(coverage.files_total),
  };

  return (
    <section aria-labelledby={COVERAGE_HEADING_ID} data-coverage="">
      <h2 id={COVERAGE_HEADING_ID} className="mb-3.5 font-condensed text-2xl font-bold tracking-[0.08em]">
        {t("heading")}
      </h2>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,320px),1fr))] items-start gap-3.5">
        <Panel label={t("checkedLabel")} testId="checked">
          <p className="mt-2 text-lg leading-[1.45]">
            <EngineText code="coverage.checked" params={counts} />
          </p>
          <p className="mt-2 text-lg leading-[1.45]">
            <EngineText code="coverage.nothing_found" />
          </p>
        </Panel>
        <Panel label={t("notCheckedLabel")} testId="not-checked">
          <ul className="mt-2">
            {coverage.not_checked.map((item, index) => (
              <NotCheckedItem key={`${item.kind}-${index}`} item={item} />
            ))}
          </ul>
          {more > 0 && (
            <p className="mt-3 text-sm text-ink2">
              <EngineText code="coverage.more" params={{ count: String(more) }} />
            </p>
          )}
        </Panel>
      </div>
    </section>
  );
}
