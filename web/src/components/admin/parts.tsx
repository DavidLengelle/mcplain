"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { SECONDARY_BUTTON_CLASS } from "@/components/account/form-parts";
import { RawText } from "@/components/raw-text";
import { share, type Days, type Read } from "@/lib/admin-dashboard";
import { cn } from "@/lib/utils";

const BAR_CLASS =
  "h-3 w-full min-w-0 appearance-none overflow-hidden rounded-full border-0 bg-panel2 [&::-webkit-progress-bar]:bg-panel2";
const BAR_NORMAL = "[&::-moz-progress-bar]:bg-accent [&::-webkit-progress-value]:bg-accent";
const BAR_ALERT = "[&::-moz-progress-bar]:bg-warn [&::-webkit-progress-value]:bg-warn";

export function useDial<T>(loader: (days: Days) => Promise<Read<T>>, days: Days, refresh: number): Read<T> | null {
  const [state, setState] = useState<{ key: string; read: Read<T> } | null>(null);
  const key = `${days}:${refresh}`;
  useEffect(() => {
    let live = true;
    void loader(days).then((read) => {
      if (live) {
        setState({ key, read });
      }
    });
    return () => {
      live = false;
    };
  }, [loader, days, key]);
  if (state === null || state.key !== key) {
    return null;
  }
  return state.read;
}

export function useDollars(): (value: number) => string {
  const format = useFormatter();
  return (value: number) => format.number(value, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

export function useDay(): (day: string) => string {
  const format = useFormatter();
  return (day: string) => {
    const moment = new Date(`${day}T00:00:00Z`);
    if (Number.isNaN(moment.getTime())) {
      return day;
    }
    return format.dateTime(moment, { day: "numeric", month: "short", timeZone: "UTC" });
  };
}

export function useMoment(): (value: string | null) => string {
  const format = useFormatter();
  return (value: string | null) => {
    if (value === null) {
      return "";
    }
    const moment = new Date(value);
    if (Number.isNaN(moment.getTime())) {
      return "";
    }
    return format.dateTime(moment, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", timeZoneName: "short" });
  };
}

export function GroupTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="font-condensed text-[30px] leading-tight font-bold">
      {children}
    </h2>
  );
}

export function DialCard({ id, title, children, testId }: { id: string; title: string; children: ReactNode; testId?: string }) {
  return (
    <section aria-labelledby={id} data-testid={testId} className="flex min-w-0 flex-col gap-3 rounded-[18px] bg-panel p-5 sm:p-6">
      <h3 id={id} className="font-condensed text-[24px] leading-tight font-bold">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function Bar({ value, max, label, alert = false }: { value: number; max: number; label: string; alert?: boolean }) {
  return (
    <progress
      value={Math.round(share(value, max) * 100)}
      max={100}
      aria-label={label}
      className={cn(BAR_CLASS, alert && BAR_ALERT, !alert && BAR_NORMAL)}
    />
  );
}

type BarRowProps = { label: string; value: number; max: number; shown: string; alert?: boolean; detail?: ReactNode; raw?: boolean };

export function BarRow({ label, value, max, shown, alert = false, detail, raw = false }: BarRowProps) {
  let name: ReactNode = label;
  if (raw) {
    name = <RawText value={label} />;
  }
  return (
    <li className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 text-[15px]">
      <span className={cn("min-w-0 text-ink2", raw && "font-mono text-sm break-all", !raw && "truncate")}>{name}</span>
      <Bar value={value} max={max} label={`${label} : ${shown}`} alert={alert} />
      <span className="text-right font-semibold text-ink tabular-nums">{shown}</span>
      {detail !== undefined && <span className="col-span-3 text-sm text-muted sm:col-span-2 sm:col-start-2">{detail}</span>}
    </li>
  );
}

export function BarList({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <ul data-testid={testId} className="flex flex-col gap-2">
      {children}
    </ul>
  );
}

export function DialMessage({ read }: { read: Read<unknown> | null }) {
  const t = useTranslations("admin.dashboard");
  if (read === null) {
    return <p className="text-muted">{t("loading")}</p>;
  }
  if (read.kind === "refused") {
    return <p className="font-semibold text-ink">{t("refused")}</p>;
  }
  if (read.kind === "unavailable") {
    return <p className="font-semibold text-ink">{t("unavailable")}</p>;
  }
  if (read.kind === "failed") {
    return <p className="font-semibold text-ink">{t("failed")}</p>;
  }
  return null;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-muted">{children}</p>;
}

export function ConfirmButton({
  label,
  question,
  confirm,
  onConfirm,
  testId,
}: {
  label: string;
  question: string;
  confirm: string;
  onConfirm: () => Promise<void>;
  testId?: string;
}) {
  const t = useTranslations("admin.dashboard");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  async function confirmed() {
    setBusy(true);
    await onConfirm();
    setBusy(false);
    setAsking(false);
  }

  if (!asking) {
    return (
      <button type="button" data-testid={testId} onClick={() => setAsking(true)} className={SECONDARY_BUTTON_CLASS}>
        {label}
      </button>
    );
  }
  return (
    <span role="group" aria-label={question} className="flex flex-wrap items-center gap-2">
      <span className="font-semibold text-ink">{question}</span>
      <button type="button" disabled={busy} onClick={() => void confirmed()} className={cn(SECONDARY_BUTTON_CLASS, "font-semibold")}>
        {confirm}
      </button>
      <button type="button" disabled={busy} onClick={() => setAsking(false)} className={SECONDARY_BUTTON_CLASS}>
        {t("cancel")}
      </button>
    </span>
  );
}
