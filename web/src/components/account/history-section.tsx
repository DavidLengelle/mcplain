"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { RawText } from "@/components/raw-text";
import { useFormattedDate } from "@/components/report/identity-line";
import { Link } from "@/i18n/navigation";
import { VERDICT_COLORS, type VerdictColor } from "@/lib/analysis";
import { clearHistory, fetchHistory, type HistoryEntry } from "@/lib/quota";
import { cn } from "@/lib/utils";

import { BUTTON_CLASS, FormMessage, LINK_CLASS, SECONDARY_BUTTON_CLASS } from "./form-parts";

const WORD_CLASS: Record<VerdictColor, string> = {
  green: "text-green",
  orange: "text-warn-text",
  red: "text-red",
  gray: "text-gray",
};

type Loaded = { kind: "loading" } | { kind: "failed" } | { kind: "ready"; entries: HistoryEntry[] };

function isColor(value: string | null): value is VerdictColor {
  return value !== null && (VERDICT_COLORS as readonly string[]).includes(value);
}

function Outcome({ entry }: { entry: HistoryEntry }) {
  const t = useTranslations("account.history");
  const verdict = useTranslations("verdict.word");
  if (entry.status === "multiple_servers") {
    return <span className="font-condensed font-bold tracking-[0.04em] text-ink2">{t("list")}</span>;
  }
  if (!isColor(entry.color)) {
    return <span className="font-condensed font-bold tracking-[0.04em] text-muted">{t("running")}</span>;
  }
  return (
    <span data-color={entry.color} className={cn("font-condensed font-bold tracking-[0.04em]", WORD_CLASS[entry.color])}>
      {verdict(entry.color)}
    </span>
  );
}

function Line({ entry }: { entry: HistoryEntry }) {
  const t = useTranslations("account.history");
  const formatDate = useFormattedDate();
  const date = formatDate(entry.date);

  return (
    <li data-testid="history-entry" className="flex flex-col gap-1 rounded-[12px] bg-panel px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="min-w-0 font-mono break-all text-ink">
          <RawText value={entry.input} />
          {entry.select !== null && (
            <span className="text-muted">
              {" "}
              <RawText value={entry.select} />
            </span>
          )}
        </span>
        <Outcome entry={entry} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
        {date !== null && <span>{date}</span>}
        {entry.fromCache && <span data-testid="history-from-cache">{t("fromCache")}</span>}
        <Link href={`/analyses/${entry.id}`} className={LINK_CLASS}>
          {t("open")}
        </Link>
      </div>
    </li>
  );
}

function ClearHistory({ onCleared }: { onCleared: () => void }) {
  const t = useTranslations("account.history");
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function confirm() {
    setPending(true);
    setFailed(false);
    const done = await clearHistory();
    setPending(false);
    if (done) {
      setOpen(false);
      onCleared();
      return;
    }
    setFailed(true);
  }

  if (!open) {
    return (
      <div>
        <button type="button" onClick={() => setOpen(true)} className={`${SECONDARY_BUTTON_CLASS} font-semibold`}>
          {t("clear")}
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="font-semibold text-ink">{t("clearConfirmIntro")}</p>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={confirm} disabled={pending} className={BUTTON_CLASS}>
          {t("clearConfirm")}
        </button>
        <button type="button" onClick={() => setOpen(false)} className={SECONDARY_BUTTON_CLASS}>
          {t("clearCancel")}
        </button>
      </div>
      <FormMessage id="history-clear-error" tone="error">
        {failed && t("error")}
      </FormMessage>
    </div>
  );
}

export function HistorySection() {
  const t = useTranslations("account.history");
  const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    void fetchHistory().then((entries) => {
      if (!active) {
        return;
      }
      if (entries === null) {
        setLoaded({ kind: "failed" });
        return;
      }
      setLoaded({ kind: "ready", entries });
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section aria-labelledby="history-heading" data-testid="history" className="flex flex-col gap-4 rounded-[14px] bg-panel2 p-5">
      <h2 id="history-heading" className="font-condensed text-[26px] font-bold text-ink">
        {t("title")}
      </h2>
      {loaded.kind === "loading" && <p>{t("loading")}</p>}
      {loaded.kind === "failed" && <p className="font-semibold text-red">{t("error")}</p>}
      {loaded.kind === "ready" && loaded.entries.length === 0 && <p data-testid="history-empty">{t("empty")}</p>}
      {loaded.kind === "ready" && loaded.entries.length > 0 && (
        <>
          <ol className="flex flex-col gap-2">
            {loaded.entries.map((entry) => (
              <Line key={`${entry.id}-${entry.date ?? ""}`} entry={entry} />
            ))}
          </ol>
          <ClearHistory onCleared={() => setLoaded({ kind: "ready", entries: [] })} />
        </>
      )}
    </section>
  );
}
