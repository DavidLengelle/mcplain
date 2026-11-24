"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { FormMessage, LINK_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { Link } from "@/i18n/navigation";
import { readAccounts, readRefusals, type ActionOutcome, type Analyses, type Counted, type Days, type Read } from "@/lib/admin-dashboard";

import { RerunButton } from "./health";
import { useOutcomeText } from "./outcome";
import { BarList, BarRow, DialCard, DialMessage, Empty, useDay, useDial } from "./parts";

const KNOWN_COLORS = new Set(["red", "orange", "gray", "green"]);
const KNOWN_REFUSALS = new Set(["signup_limit", "quota_exhausted_anonymous", "quota_exhausted_account", "report_limit", "report_global"]);

function highestOf(items: Counted[]): number {
  return Math.max(0, ...items.map((item) => item.count));
}

function CodeList({ items, testId, empty }: { items: Counted[]; testId: string; empty: string }) {
  if (items.length === 0) {
    return <Empty>{empty}</Empty>;
  }
  const highest = highestOf(items);
  return (
    <BarList testId={testId}>
      {items.map((item) => (
        <BarRow key={item.code} label={item.code} value={item.count} max={highest} shown={String(item.count)} raw />
      ))}
    </BarList>
  );
}

function AnalysesPerDay({ analyses }: { analyses: Analyses }) {
  const t = useTranslations("admin.dashboard.analyses");
  const day = useDay();
  const highest = Math.max(0, ...analyses.perDay.map((item) => item.total));
  const total = analyses.perDay.reduce((count, item) => count + item.total, 0);
  const cached = analyses.perDay.reduce((count, item) => count + item.cached, 0);
  return (
    <>
      <p data-testid="admin-analyses-total" className="font-semibold text-ink">
        {t("total", { total, cached, fresh: total - cached })}
      </p>
      <BarList testId="admin-analyses-days">
        {analyses.perDay.map((item) => (
          <BarRow key={item.day} label={day(item.day)} value={item.total} max={highest} shown={String(item.total)} detail={t("dayDetail", { cached: item.cached, fresh: item.fresh })} />
        ))}
      </BarList>
    </>
  );
}

function Colors({ analyses }: { analyses: Analyses }) {
  const t = useTranslations("admin.dashboard.colors");
  const highest = highestOf(analyses.colors);
  return (
    <>
      <BarList testId="admin-colors">
        {analyses.colors
          .filter((item) => KNOWN_COLORS.has(item.code))
          .map((item) => (
            <BarRow key={item.code} label={t(item.code)} value={item.count} max={highest} shown={String(item.count)} />
          ))}
      </BarList>
      <h4 className="font-semibold text-ink">{t("grayCases")}</h4>
      <CodeList items={analyses.grayCases} testId="admin-gray-cases" empty={t("noGray")} />
    </>
  );
}

function Top({ analyses, onChanged }: { analyses: Analyses; onChanged: (outcome: ActionOutcome) => void }) {
  const t = useTranslations("admin.dashboard.top");
  if (analyses.top.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  return (
    <ol data-testid="admin-top" className="flex flex-col gap-2">
      {analyses.top.map((item, index) => (
        <li key={`${item.kind}:${item.name}`} className="flex flex-col gap-1.5 rounded-[12px] bg-panel2 p-3">
          <p className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 text-ink">
            <span className="font-semibold tabular-nums text-muted">{index + 1}.</span>
            <span className="min-w-0 font-mono font-semibold break-all">
              <RawText value={item.name} />
            </span>
            <span className="font-mono text-sm text-muted">
              <RawText value={item.kind} />
            </span>
            <span className="font-semibold tabular-nums">{t("count", { count: item.count })}</span>
          </p>
          {item.lastAnalysisId !== null && (
            <div className="flex flex-wrap items-center gap-3">
              <Link href={`/analyses/${item.lastAnalysisId}`} className={LINK_CLASS}>
                {t("lastReport")}
              </Link>
              <RerunButton analysisId={item.lastAnalysisId} onChanged={onChanged} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

function Languages({ analyses }: { analyses: Analyses }) {
  const t = useTranslations("admin.dashboard.languages");
  if (analyses.languages.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  const highest = highestOf(analyses.languages);
  return (
    <BarList testId="admin-languages">
      {analyses.languages.map((item) => (
        <BarRow key={item.code} label={item.code} value={item.count} max={highest} shown={String(item.count)} raw />
      ))}
    </BarList>
  );
}

function refusalLabel(t: ReturnType<typeof useTranslations>, kind: string): string {
  if (KNOWN_REFUSALS.has(kind)) {
    return t(`kind.${kind}`);
  }
  return kind;
}

function RefusalsDial({ days, refresh }: { days: Days; refresh: number }) {
  const t = useTranslations("admin.dashboard.refusals");
  const read = useDial(readRefusals, days, refresh);
  const day = useDay();
  if (read === null || read.kind !== "ready") {
    return <DialMessage read={read} />;
  }
  const refusals = read.value;
  const totals = refusals.perDay.map((item) => item.counts.reduce((count, entry) => count + entry.count, 0));
  const highest = Math.max(0, ...totals);
  return (
    <>
      <ul data-testid="admin-refusal-totals" className="flex flex-col gap-1 text-ink">
        {refusals.totals.map((item) => (
          <li key={item.code}>
            {refusalLabel(t, item.code)} : <span className="font-semibold tabular-nums">{item.count}</span>
          </li>
        ))}
      </ul>
      <h4 className="font-semibold text-ink">{t("perDay")}</h4>
      <BarList testId="admin-refusal-days">
        {refusals.perDay.map((item, index) => (
          <BarRow
            key={item.day}
            label={day(item.day)}
            value={totals[index] ?? 0}
            max={highest}
            shown={String(totals[index] ?? 0)}
            detail={item.counts
              .filter((entry) => entry.count > 0)
              .map((entry) => `${refusalLabel(t, entry.code)} ${entry.count}`)
              .join(" · ")}
          />
        ))}
      </BarList>
    </>
  );
}

function AccountsDial({ days, refresh }: { days: Days; refresh: number }) {
  const t = useTranslations("admin.dashboard.accounts");
  const read = useDial(readAccounts, days, refresh);
  const day = useDay();
  if (read === null || read.kind !== "ready") {
    return <DialMessage read={read} />;
  }
  const highest = Math.max(0, ...read.value.perDay.map((item) => item.count));
  return (
    <>
      <p data-testid="admin-accounts-total" className="font-semibold text-ink">
        {t("total", { count: read.value.total })}
      </p>
      <BarList testId="admin-accounts-days">
        {read.value.perDay.map((item) => (
          <BarRow key={item.day} label={day(item.day)} value={item.count} max={highest} shown={String(item.count)} />
        ))}
      </BarList>
    </>
  );
}

export function UsageGroup({ analyses, days, refresh, onChanged }: { analyses: Read<Analyses> | null; days: Days; refresh: number; onChanged: () => void }) {
  const t = useTranslations("admin.dashboard");
  const outcomeText = useOutcomeText();
  const [outcome, setOutcome] = useState<ActionOutcome | null>(null);
  const ready = analyses !== null && analyses.kind === "ready";

  function changed(result: ActionOutcome) {
    setOutcome(result);
    onChanged();
  }

  return (
    <>
      <DialCard id="admin-analyses-title" title={t("analyses.title")} testId="admin-analyses-dial">
        {ready && <AnalysesPerDay analyses={analyses.value} />}
        {!ready && <DialMessage read={analyses} />}
      </DialCard>
      <DialCard id="admin-colors-title" title={t("colors.title")} testId="admin-colors-dial">
        {ready && <Colors analyses={analyses.value} />}
        {!ready && <DialMessage read={analyses} />}
      </DialCard>
      <DialCard id="admin-top-title" title={t("top.title")} testId="admin-top-dial">
        <FormMessage id="admin-top-message" tone="info">
          {outcome !== null && outcomeText(outcome)}
        </FormMessage>
        {ready && <Top analyses={analyses.value} onChanged={changed} />}
        {!ready && <DialMessage read={analyses} />}
      </DialCard>
      <DialCard id="admin-languages-title" title={t("languages.title")} testId="admin-languages-dial">
        {ready && <Languages analyses={analyses.value} />}
        {!ready && <DialMessage read={analyses} />}
      </DialCard>
      <DialCard id="admin-refusals-title" title={t("refusals.title")} testId="admin-refusals-dial">
        <RefusalsDial days={days} refresh={refresh} />
      </DialCard>
      <DialCard id="admin-visits-title" title={t("accounts.title")} testId="admin-visits-dial">
        <AccountsDial days={days} refresh={refresh} />
      </DialCard>
    </>
  );
}
