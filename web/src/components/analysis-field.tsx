"use client";

import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { INPUT_MAX_CHARACTERS } from "@/lib/api-client";
import { EXAMPLES, exampleLabel } from "@/lib/constants";
import { cn } from "@/lib/utils";

import { StartErrorText } from "./start-error";
import { SubmitLabel } from "./submit-label";
import { useAnalysisStart } from "./use-analysis-start";

export const HEADER_INPUT_ID = "header-input";
export const HOME_INPUT_ID = "home-input";

export type FieldVariant = "header" | "hero";

const IDS: Record<FieldVariant, { input: string; error: string }> = {
  header: { input: HEADER_INPUT_ID, error: "header-error" },
  hero: { input: HOME_INPUT_ID, error: "home-error" },
};

const FORM: Record<FieldVariant, string> = {
  header: "flex min-w-0 flex-[999_1_380px] flex-col gap-1",
  hero: "mt-7 flex min-w-0 flex-col",
};

const ROW: Record<FieldVariant, string> = {
  header: "flex min-w-0 gap-2",
  hero: "flex min-w-0 flex-wrap gap-2.5",
};

const INPUT: Record<FieldVariant, string> = {
  header: "h-12 flex-1 rounded-[10px] bg-input-bg px-4 text-sm",
  hero: "h-[60px] flex-[999_1_300px] rounded-xl bg-panel2 px-[18px] text-base",
};

const BUTTON: Record<FieldVariant, string> = {
  header: "h-12 shrink-0 rounded-[10px] px-[22px] text-[19px]",
  hero: "h-[60px] flex-[1_0_auto] rounded-xl px-[30px] text-[22px]",
};

const ERROR: Record<FieldVariant, string> = {
  header: "text-sm",
  hero: "text-[15px]",
};

function FieldLabel({ variant, htmlFor, children }: { variant: FieldVariant; htmlFor: string; children: string }) {
  if (variant === "header") {
    return (
      <label htmlFor={htmlFor} className="sr-only">
        {children}
      </label>
    );
  }
  return (
    <label htmlFor={htmlFor} className="mb-2 block text-[15px] font-semibold">
      {children}
    </label>
  );
}

export function AnalysisField({ variant }: { variant: FieldVariant }) {
  const t = useTranslations("header");
  const home = useTranslations("home.tool");
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const { pending, error, start, clearError } = useAnalysisStart();
  const ids = IDS[variant];
  let label = t("inputLabel");
  if (variant === "hero") {
    label = home("label");
  }

  async function run(text: string) {
    const accepted = await start(text);
    if (!accepted) {
      input.current?.focus();
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(value);
  }

  async function tryExample(example: string) {
    setValue(example);
    clearError();
    await run(example);
  }

  return (
    <form onSubmit={submit} noValidate className={FORM[variant]} data-analysis-field={variant}>
      <FieldLabel variant={variant} htmlFor={ids.input}>
        {label}
      </FieldLabel>
      <div className={ROW[variant]}>
        <input
          ref={input}
          id={ids.input}
          name="input"
          type="text"
          value={value}
          maxLength={INPUT_MAX_CHARACTERS}
          placeholder={t("placeholder")}
          onChange={(event) => {
            setValue(event.target.value);
            clearError();
          }}
          aria-describedby={ids.error}
          aria-invalid={error !== null}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className={cn("min-w-0 border-2 border-input-border font-mono text-ink", INPUT[variant])}
        />
        <button
          type="submit"
          disabled={pending}
          className={cn(
            "cursor-pointer bg-accent font-condensed font-bold tracking-[0.06em] text-on-accent hover:bg-accent-hover disabled:cursor-wait",
            BUTTON[variant],
          )}
        >
          <SubmitLabel idle={t("submit")} busy={t("submitting")} pending={pending} />
        </button>
      </div>
      <p id={ids.error} aria-live="polite" className={cn("font-semibold text-red", ERROR[variant])}>
        {error !== null && (
          <span className={cn("block", variant === "hero" && "pt-2.5")}>
            <StartErrorText error={error} />
          </span>
        )}
      </p>
      {variant === "hero" && (
        <div className="mt-3.5 flex flex-wrap items-center gap-x-2.5 gap-y-2">
          <span className="text-sm text-muted">{home("examples")}</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              disabled={pending}
              onClick={() => tryExample(example)}
              aria-label={home("exampleLabel", { example: exampleLabel(example) })}
              data-example={example}
              className="min-h-11 max-w-full cursor-pointer rounded-[10px] border-[1.5px] border-btn-border bg-transparent px-3.5 py-1.5 text-left font-mono text-[13px] break-all text-ink transition-colors hover:bg-row-hover disabled:cursor-wait motion-reduce:transition-none"
            >
              {exampleLabel(example)}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
