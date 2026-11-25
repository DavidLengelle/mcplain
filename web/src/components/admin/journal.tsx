"use client";

import { useTranslations } from "next-intl";

import { LINK_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { Link } from "@/i18n/navigation";
import { readJournal, type Days } from "@/lib/admin-dashboard";

import { DialMessage, Empty, useDial, useMoment } from "./parts";

const KNOWN_ACTIONS = new Set([
  "ban",
  "unban",
  "text_retry",
  "analysis_rerun",
  "alert_read",
  "credit_add",
  "credit_delete",
  "report_handled",
  "report_rejected",
]);
const KNOWN_TARGETS = new Set(["account", "analysis", "text", "alert", "credit", "report"]);

function readJournalAnyDays(): ReturnType<typeof readJournal> {
  return readJournal();
}

export function Journal({ days, refresh }: { days: Days; refresh: number }) {
  const t = useTranslations("admin.dashboard.journal");
  const read = useDial(readJournalAnyDays, days, refresh);
  const moment = useMoment();
  if (read === null || read.kind !== "ready") {
    return <DialMessage read={read} />;
  }
  if (read.value.length === 0) {
    return <Empty>{t("none")}</Empty>;
  }
  return (
    <ol data-testid="admin-journal" className="flex flex-col gap-2">
      {read.value.map((line) => {
        let action = line.action;
        if (KNOWN_ACTIONS.has(line.action)) {
          action = t(`action.${line.action}`);
        }
        let target = line.targetKind;
        if (KNOWN_TARGETS.has(line.targetKind)) {
          target = t(`target.${line.targetKind}`);
        }
        return (
          <li key={line.id} className="flex flex-col gap-1 rounded-[12px] bg-panel2 p-3 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-4">
            <span className="text-sm text-muted">{moment(line.createdAt)}</span>
            <span className="font-semibold text-ink">{action}</span>
            <span className="text-ink2">{target}</span>
            <span className="min-w-0 font-mono text-sm [overflow-wrap:anywhere] text-ink2">
              <RawText value={line.targetId} />
            </span>
            {line.targetKind === "analysis" && (
              <Link href={`/analyses/${encodeURIComponent(line.targetId)}`} className={LINK_CLASS}>
                {t("report")}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}
