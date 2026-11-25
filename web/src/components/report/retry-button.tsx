"use client";

import { useTranslations } from "next-intl";

import { BUTTON_CLASS } from "../account/form-parts";
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
        className={BUTTON_CLASS}
      >
        {label}
      </button>
      <p aria-live="polite" className="font-semibold [overflow-wrap:anywhere] text-red">
        {error !== null && <StartErrorText error={error} />}
      </p>
    </div>
  );
}
