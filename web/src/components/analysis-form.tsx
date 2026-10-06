"use client";

import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { INPUT_MAX_CHARACTERS } from "@/lib/api-client";
import { EXAMPLES } from "@/lib/constants";

import { StartErrorText } from "./start-error";
import { useAnalysisStart } from "./use-analysis-start";

export function AnalysisForm() {
  const t = useTranslations("form");
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const { pending, error, start, clearError } = useAnalysisStart();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const accepted = await start(value);
    if (!accepted) {
      input.current?.focus();
    }
  }

  function fill(example: string) {
    setValue(example);
    clearError();
    input.current?.focus();
  }

  let submitLabel = t("submit");
  if (pending) {
    submitLabel = t("submitting");
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3">
      <label htmlFor="analysis-input" className="text-lg font-semibold">
        {t("label")}
      </label>
      <p id="analysis-hint" className="text-sm text-muted">
        {t("hint")}
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          ref={input}
          id="analysis-input"
          name="input"
          type="text"
          value={value}
          maxLength={INPUT_MAX_CHARACTERS}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby="analysis-hint analysis-error"
          aria-invalid={error !== null}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="h-12 min-w-0 flex-1 rounded-[10px] border-2 border-input-border bg-input-bg px-4 font-mono text-base text-ink"
        />
        <button
          type="submit"
          disabled={pending}
          className="h-12 cursor-pointer rounded-[10px] bg-accent px-[22px] font-condensed text-[19px] font-bold tracking-[0.06em] text-on-accent hover:bg-accent-hover disabled:cursor-wait"
        >
          {submitLabel}
        </button>
      </div>
      <p id="analysis-error" aria-live="polite" className="min-h-6 font-semibold text-red">
        {error !== null && <StartErrorText error={error} />}
      </p>
      <div className="flex flex-col gap-2">
        <p className="font-semibold">{t("examples")}</p>
        <ul className="flex flex-col items-start gap-2">
          {EXAMPLES.map((example) => (
            <li key={example} className="max-w-full">
              <button
                type="button"
                onClick={() => fill(example)}
                aria-label={t("exampleLabel", { example })}
                className="min-h-11 max-w-full cursor-pointer rounded-[10px] border-[1.5px] border-btn-border px-3 py-1.5 text-left font-mono text-sm break-all text-ink hover:bg-row-hover"
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}
