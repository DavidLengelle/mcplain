"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cutText, splitInvisible } from "@/lib/invisible";
import { cn } from "@/lib/utils";

export const RAW_TEXT_LIMIT = 400;

type RawTextProps = {
  value: string;
  limit?: number;
  variant?: "inline" | "block";
  className?: string;
};

function InvisibleBadge({ label }: { label: string }) {
  const t = useTranslations("rawText");

  return (
    <span
      title={t("invisible")}
      data-invisible={label}
      className="mx-0.5 inline-block rounded-sm border border-yellow-800 bg-yellow-100 px-1 font-mono text-[0.8em] font-bold text-yellow-950 not-italic dark:border-yellow-300 dark:bg-yellow-950 dark:text-yellow-50"
    >
      <span aria-hidden="true">⟨</span>
      {label}
      <span aria-hidden="true">⟩</span>
      <span className="sr-only"> {t("invisible")}</span>
    </span>
  );
}

function ToggleButton({ expanded, onToggle }: { expanded: boolean; onToggle: () => void }) {
  const t = useTranslations("rawText");
  let label = t("showAll");
  if (expanded) {
    label = t("showLess");
  }

  return (
    <button
      type="button"
      aria-expanded={expanded}
      onClick={onToggle}
      className="ml-1 rounded-sm font-sans text-sm font-semibold underline underline-offset-4 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {label}
    </button>
  );
}

export function RawText({ value, limit = RAW_TEXT_LIMIT, variant = "inline", className }: RawTextProps) {
  const [expanded, setExpanded] = useState(false);
  const shortened = cutText(value, limit);
  let shown = value;
  if (shortened.cut && !expanded) {
    shown = shortened.text;
  }
  const pieces = splitInvisible(shown);
  const isolated = (
    <bdi
      data-raw-text=""
      className={cn(
        "font-mono whitespace-pre-wrap [overflow-wrap:anywhere] [unicode-bidi:isolate]",
        variant === "inline" && "rounded-sm bg-muted px-1 text-[0.95em]",
        className,
      )}
    >
      {pieces.map((piece, index) => {
        if (piece.kind === "text") {
          return <span key={index}>{piece.text}</span>;
        }
        return <InvisibleBadge key={index} label={piece.label} />;
      })}
      {shortened.cut && !expanded && <span aria-hidden="true">…</span>}
    </bdi>
  );
  const toggle = shortened.cut && <ToggleButton expanded={expanded} onToggle={() => setExpanded(!expanded)} />;

  if (variant === "block") {
    return (
      <div className="rounded-md border border-border bg-muted p-3 text-sm">
        {isolated}
        {toggle && <div className="mt-2">{toggle}</div>}
      </div>
    );
  }
  return (
    <>
      {isolated}
      {toggle}
    </>
  );
}
