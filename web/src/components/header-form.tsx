"use client";

import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { INPUT_MAX_CHARACTERS } from "@/lib/api-client";

import { StartErrorText } from "./start-error";
import { useAnalysisStart } from "./use-analysis-start";

export const HEADER_INPUT_ID = "header-input";

export function HeaderForm() {
  const t = useTranslations("header");
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

  let submitLabel = t("submit");
  if (pending) {
    submitLabel = t("submitting");
  }

  return (
    <form onSubmit={submit} noValidate className="flex min-w-0 flex-[999_1_380px] flex-col gap-1">
      <div className="flex min-w-0 gap-2">
        <label htmlFor={HEADER_INPUT_ID} className="sr-only">
          {t("inputLabel")}
        </label>
        <input
          ref={input}
          id={HEADER_INPUT_ID}
          name="input"
          type="text"
          value={value}
          maxLength={INPUT_MAX_CHARACTERS}
          placeholder={t("placeholder")}
          onChange={(event) => {
            setValue(event.target.value);
            clearError();
          }}
          aria-describedby="header-error"
          aria-invalid={error !== null}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="h-12 min-w-0 flex-1 rounded-[10px] border-2 border-input-border bg-input-bg px-4 font-mono text-sm text-ink"
        />
        <button
          type="submit"
          disabled={pending}
          className="h-12 shrink-0 cursor-pointer rounded-[10px] bg-accent px-[22px] font-condensed text-[19px] font-bold tracking-[0.06em] text-on-accent hover:bg-accent-hover disabled:cursor-wait"
        >
          {submitLabel}
        </button>
      </div>
      <p id="header-error" aria-live="polite" className="text-sm font-semibold text-red">
        {error !== null && <StartErrorText error={error} />}
      </p>
    </form>
  );
}
