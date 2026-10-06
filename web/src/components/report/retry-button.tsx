"use client";

import { useTranslations } from "next-intl";

import { StartErrorText } from "../start-error";
import { useAnalysisStart } from "../use-analysis-start";

export function RetryButton({ input, select }: { input: string; select: string | null }) {
  const t = useTranslations("verdict");
  const { pending, error, start } = useAnalysisStart();
  let label = t("retry");
  if (pending) {
    label = t("retrying");
  }

  return (
    <div className="mt-5 flex flex-col items-start gap-2">
      <button
        type="button"
        disabled={pending}
        onClick={() => start(input, select)}
        data-retry=""
        className="min-h-11 cursor-pointer rounded-[10px] bg-accent px-5 font-condensed text-lg font-bold tracking-[0.06em] text-on-accent hover:bg-accent-hover disabled:cursor-wait"
      >
        {label}
      </button>
      <p aria-live="polite" className="font-semibold text-red">
        {error !== null && <StartErrorText error={error} />}
      </p>
    </div>
  );
}
