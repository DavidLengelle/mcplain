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
  expandable?: boolean;
  className?: string;
};

function InvisibleBadge({ label }: { label: string }) {
  const t = useTranslations("rawText");

  return (
    <span
      title={t("invisible")}
      data-invisible={label}
      className="mx-0.5 inline-block rounded-sm border border-warn bg-warn-note px-1 font-mono text-[0.8em] font-bold text-warn-text not-italic"
    >
      <span aria-hidden="true">⟨</span>
      {label}
      <span aria-hidden="true">⟩</span>
      <span className="sr-only"> {t("invisible")}</span>
    </span>
  );
}

function ToggleButton({ expanded, onToggle, tall }: { expanded: boolean; onToggle: () => void; tall: boolean }) {
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
      className={cn(
        "ml-1 rounded-sm font-sans text-sm font-semibold text-accent underline underline-offset-4 hover:text-accent-hover",
        tall && "inline-flex min-h-11 items-center",
      )}
    >
      {label}
    </button>
  );
}

export function RawText({
  value,
  limit = RAW_TEXT_LIMIT,
  variant = "inline",
  expandable = true,
  className,
}: RawTextProps) {
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
        variant === "inline" && "text-[0.95em]",
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
  const toggle = shortened.cut && expandable && (
    <ToggleButton expanded={expanded} onToggle={() => setExpanded(!expanded)} tall={variant === "block"} />
  );

  if (variant === "block") {
    return (
      <div className="rounded-lg bg-code-bg px-3 py-2.5 text-sm leading-relaxed text-ink">
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
