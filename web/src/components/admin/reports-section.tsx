"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { FormMessage, LINK_CLASS, SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { Link } from "@/i18n/navigation";
import { readReportsPerDay, type Days } from "@/lib/admin-dashboard";
import {
  changeReportStatus,
  readReportList,
  REPORT_KINDS,
  REPORT_STATUSES,
  type ListRead,
  type ReportKind,
  type ReportStatus,
  type VisitorReport,
} from "@/lib/visitor-reports";
import { cn } from "@/lib/utils";

import { BarList, BarRow, DialMessage, Empty, useDay, useDial, useMoment } from "./parts";

const KNOWN_COLORS = new Set(["red", "orange", "gray", "green"]);
const KNOWN_KINDS = new Set<string>(REPORT_KINDS);
const KNOWN_STATUSES = new Set<string>(REPORT_STATUSES);
const KNOWN_REPORTERS = new Set(["anonymous", "account", "deleted"]);
const ALL = "all";

function useReportList(status: ReportStatus | null, kind: ReportKind | null, refresh: number): ListRead | null {
  const [state, setState] = useState<{ key: string; read: ListRead } | null>(null);
  const key = `${status ?? ALL}:${kind ?? ALL}:${refresh}`;
  useEffect(() => {
    let live = true;
    void readReportList(status, kind).then((read) => {
      if (live) {
        setState({ key, read });
      }
    });
    return () => {
      live = false;
    };
  }, [status, kind, key]);
  if (state === null || state.key !== key) {
    return null;
  }
  return state.read;
}

function statusOf(value: string): ReportStatus | null {
  if (KNOWN_STATUSES.has(value)) {
    return value as ReportStatus;
  }
  return null;
}

function kindOf(value: string): ReportKind | null {
  if (KNOWN_KINDS.has(value)) {
    return value as ReportKind;
  }
  return null;
}

export function NewReportsCount({ refresh }: { refresh: number }) {
  const t = useTranslations("admin.reports");
  const read = useReportList("new", null, refresh);
  if (read === null || read.kind !== "ready") {
    return null;
  }
  const count = read.value.newCount;
  return (
    <p data-testid="admin-new-reports" className={cn("font-semibold", count > 0 && "text-warn-text", count === 0 && "text-ink2")}>
      {t("newCount", { count })}
    </p>
  );
}

function ReportLine({ report, onChanged }: { report: VisitorReport; onChanged: (done: boolean) => void }) {
  const t = useTranslations("admin.reports");
  const colors = useTranslations("admin.dashboard.colors");
  const moment = useMoment();
  const [busy, setBusy] = useState(false);

  async function change(status: "handled" | "rejected") {
    setBusy(true);
    const done = await changeReportStatus(report.id, status);
    setBusy(false);
    onChanged(done);
  }

  let kind = report.kind;
  if (KNOWN_KINDS.has(report.kind)) {
    kind = t(`kind.${report.kind}`);
  }
  let status = report.status;
  if (KNOWN_STATUSES.has(report.status)) {
    status = t(`status.${report.status}`);
  }
  let color = report.color ?? "-";
  if (report.color !== null && KNOWN_COLORS.has(report.color)) {
    color = colors(report.color);
  }
  let reporter = report.reporterKind;
  if (KNOWN_REPORTERS.has(report.reporterKind)) {
    reporter = t(`reporter.${report.reporterKind}`);
  }

  return (
    <li
      data-testid="admin-report"
      data-report-status={report.status}
      className={cn("flex flex-col gap-2 rounded-[12px] bg-panel2 p-3", report.status === "new" && "border-l-4 border-warn")}
    >
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold text-ink">{kind}</span>
        {report.unverified && (
          <span data-testid="admin-report-unverified" className="rounded-full border border-line px-2 text-sm font-semibold text-ink2">
            {t("unverified")}
          </span>
        )}
        <span className={cn("font-semibold", report.status === "new" && "text-warn-text", report.status !== "new" && "text-ink2")}>
          {status}
        </span>
        <span className="text-sm text-muted">{t("sentAt", { date: moment(report.createdAt) })}</span>
      </p>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm text-ink2 sm:grid-cols-[auto_minmax(0,1fr)]">
        <dt className="font-semibold">{t("colorLabel")}</dt>
        <dd>{color}</dd>
        <dt className="font-semibold">{t("versionsLabel")}</dt>
        <dd className="font-mono break-all">
          <RawText value={t("versions", { engine: report.engineVersion ?? "-", rules: report.rulesVersion ?? "-" })} />
        </dd>
        <dt className="font-semibold">{t("reporterLabel")}</dt>
        <dd className="flex min-w-0 flex-wrap gap-x-2">
          <span>{reporter}</span>
          {report.accountId !== null && (
            <span data-testid="admin-report-account" className="min-w-0 font-mono break-all">
              <RawText value={report.accountId} />
            </span>
          )}
        </dd>
      </dl>
      <div data-testid="admin-report-comment" className="text-ink">
        {report.comment !== null && (
          <p className="break-words whitespace-pre-wrap">
            <RawText value={report.comment} />
          </p>
        )}
        {report.comment === null && report.commentErasedAt !== null && <p className="text-muted">{t("erased")}</p>}
        {report.comment === null && report.commentErasedAt === null && <p className="text-muted">{t("noComment")}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {report.analysisId !== null && (
          <Link href={`/analyses/${encodeURIComponent(report.analysisId)}`} className={LINK_CLASS}>
            {t("report")}
          </Link>
        )}
        {report.status !== "handled" && (
          <button type="button" disabled={busy} onClick={() => void change("handled")} data-testid="admin-report-handled" className={SECONDARY_BUTTON_CLASS}>
            {t("markHandled")}
          </button>
        )}
        {report.status !== "rejected" && (
          <button type="button" disabled={busy} onClick={() => void change("rejected")} data-testid="admin-report-rejected" className={SECONDARY_BUTTON_CLASS}>
            {t("markRejected")}
          </button>
        )}
      </div>
    </li>
  );
}

function Filter({ id, label, value, options, onPick }: { id: string; label: string; value: string; options: { value: string; label: string }[]; onPick: (value: string) => void }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[15px] font-semibold text-ink">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onPick(event.target.value)}
        className="h-11 min-w-0 rounded-[10px] border-2 border-input-border bg-input-bg px-3 text-base text-ink"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ReportsSection({ refresh, onChanged }: { refresh: number; onChanged: () => void }) {
  const t = useTranslations("admin.reports");
  const [status, setStatus] = useState(ALL);
  const [kind, setKind] = useState(ALL);
  const [message, setMessage] = useState<boolean | null>(null);
  const read = useReportList(statusOf(status), kindOf(kind), refresh);

  function changed(done: boolean) {
    setMessage(done);
    onChanged();
  }

  const statusOptions = [{ value: ALL, label: t("all") }, ...REPORT_STATUSES.map((item) => ({ value: item, label: t(`status.${item}`) }))];
  const kindOptions = [{ value: ALL, label: t("all") }, ...REPORT_KINDS.map((item) => ({ value: item, label: t(`kind.${item}`) }))];

  return (
    <>
      <p className="text-ink2">{t("intro")}</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Filter id="admin-reports-status" label={t("statusLabel")} value={status} options={statusOptions} onPick={setStatus} />
        <Filter id="admin-reports-kind" label={t("kindLabel")} value={kind} options={kindOptions} onPick={setKind} />
      </div>
      <FormMessage id="admin-reports-message" tone="info">
        {message === true && t("changed")}
        {message === false && t("failed")}
      </FormMessage>
      {read !== null && read.kind === "ready" && read.value.reports.length === 0 && <Empty>{t("none")}</Empty>}
      {read !== null && read.kind === "ready" && read.value.reports.length > 0 && (
        <ul data-testid="admin-reports" className="flex flex-col gap-2">
          {read.value.reports.map((report) => (
            <ReportLine key={report.id} report={report} onChanged={changed} />
          ))}
        </ul>
      )}
      {(read === null || read.kind !== "ready") && <DialMessage read={read} />}
    </>
  );
}

export function ReportsPerDay({ days, refresh }: { days: Days; refresh: number }) {
  const t = useTranslations("admin.reports");
  const read = useDial(readReportsPerDay, days, refresh);
  const day = useDay();
  if (read === null || read.kind !== "ready") {
    return <DialMessage read={read} />;
  }
  const perDay = read.value.perDay;
  const totals = perDay.map((item) => item.counts.reduce((count, entry) => count + entry.count, 0));
  const highest = Math.max(0, ...totals);
  const kindLabel = (code: string) => {
    if (KNOWN_KINDS.has(code)) {
      return t(`kind.${code}`);
    }
    return code;
  };
  return (
    <>
      <ul data-testid="admin-report-totals" className="flex flex-col gap-1 text-ink">
        {read.value.totals.map((item) => (
          <li key={item.code}>
            {kindLabel(item.code)} : <span className="font-semibold tabular-nums">{item.count}</span>
          </li>
        ))}
      </ul>
      <BarList testId="admin-report-days">
        {perDay.map((item, index) => (
          <BarRow
            key={item.day}
            label={day(item.day)}
            value={totals[index] ?? 0}
            max={highest}
            shown={String(totals[index] ?? 0)}
            detail={item.counts
              .filter((entry) => entry.count > 0)
              .map((entry) => `${kindLabel(entry.code)} ${entry.count}`)
              .join(" · ")}
          />
        ))}
      </BarList>
    </>
  );
}
