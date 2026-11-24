"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { DAY_CHOICES, DEFAULT_DAYS, readAiHealth, readAnalyses, type Days } from "@/lib/admin-dashboard";
import { cn } from "@/lib/utils";

import { HealthGroup } from "./health";
import { Journal } from "./journal";
import { BalanceDial, SpendDial } from "./money";
import { DialCard, GroupTitle, useDial } from "./parts";
import { UsageGroup } from "./usage";

function PeriodPicker({ days, onPick }: { days: Days; onPick: (days: Days) => void }) {
  const t = useTranslations("admin.dashboard");
  return (
    <div role="group" aria-label={t("periodLabel")} className="inline-flex rounded-[10px] bg-toggle-bg p-1">
      {DAY_CHOICES.map((choice) => {
        const active = choice === days;
        return (
          <button
            key={choice}
            type="button"
            aria-pressed={active}
            onClick={() => onPick(choice)}
            className={cn("min-h-11 cursor-pointer rounded-[8px] px-4 font-semibold", active && "bg-toggle-on-bg text-toggle-on-fg", !active && "text-toggle-fg")}
          >
            {t("period", { days: choice })}
          </button>
        );
      })}
    </div>
  );
}

export function Dashboard() {
  const t = useTranslations("admin.dashboard");
  const [days, setDays] = useState<Days>(DEFAULT_DAYS);
  const [refresh, setRefresh] = useState(0);
  const ai = useDial(readAiHealth, days, refresh);
  const analyses = useDial(readAnalyses, days, refresh);

  function changed() {
    setRefresh((count) => count + 1);
  }

  return (
    <div data-testid="admin-dashboard" className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 rounded-[18px] bg-panel p-5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:p-6">
        <p className="text-ink2">{t("intro")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <PeriodPicker days={days} onPick={setDays} />
          <button type="button" onClick={changed} className={SECONDARY_BUTTON_CLASS}>
            {t("refresh")}
          </button>
        </div>
      </div>
      <section aria-labelledby="admin-money-title" className="flex flex-col gap-4">
        <GroupTitle id="admin-money-title">{t("groups.money")}</GroupTitle>
        <SpendDial days={days} refresh={refresh} />
        <BalanceDial days={days} refresh={refresh} onChanged={changed} />
      </section>
      <section aria-labelledby="admin-health-title" className="flex flex-col gap-4">
        <GroupTitle id="admin-health-title">{t("groups.health")}</GroupTitle>
        <HealthGroup ai={ai} analyses={analyses} onChanged={changed} />
      </section>
      <section aria-labelledby="admin-usage-title" className="flex flex-col gap-4">
        <GroupTitle id="admin-usage-title">{t("groups.usage")}</GroupTitle>
        <UsageGroup analyses={analyses} days={days} refresh={refresh} onChanged={changed} />
      </section>
      <DialCard id="admin-journal-title" title={t("journal.title")} testId="admin-journal-dial">
        <Journal days={days} refresh={refresh} />
      </DialCard>
    </div>
  );
}
