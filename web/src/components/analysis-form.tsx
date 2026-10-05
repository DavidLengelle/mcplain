"use client";

import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRouter } from "@/i18n/navigation";
import { INPUT_MAX_CHARACTERS, startAnalysis } from "@/lib/api-client";
import { EXAMPLES } from "@/lib/constants";

import { StartErrorText, type StartError } from "./start-error";

export function AnalysisForm() {
  const t = useTranslations("form");
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [error, setError] = useState<StartError | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = value.trim().slice(0, INPUT_MAX_CHARACTERS);
    if (text === "") {
      setError({ kind: "empty" });
      input.current?.focus();
      return;
    }
    setPending(true);
    setError(null);
    const outcome = await startAnalysis(text);
    if (outcome.kind === "accepted") {
      router.push(`/analyses/${outcome.id}`);
      return;
    }
    setPending(false);
    setError(outcome);
    input.current?.focus();
  }

  function fill(example: string) {
    setValue(example);
    setError(null);
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
      <p id="analysis-hint" className="text-sm text-muted-foreground">
        {t("hint")}
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          ref={input}
          id="analysis-input"
          name="input"
          value={value}
          maxLength={INPUT_MAX_CHARACTERS}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby="analysis-hint analysis-error"
          aria-invalid={error !== null}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="h-11 font-mono text-base md:text-base"
        />
        <Button type="submit" disabled={pending} className="h-11 px-5 text-base">
          {submitLabel}
        </Button>
      </div>
      <p id="analysis-error" aria-live="polite" className="min-h-6 font-semibold text-destructive">
        {error !== null && <StartErrorText error={error} />}
      </p>
      <div className="flex flex-col gap-2">
        <p className="font-semibold">{t("examples")}</p>
        <ul className="flex flex-col items-start gap-2">
          {EXAMPLES.map((example) => (
            <li key={example} className="max-w-full">
              <Button
                type="button"
                variant="outline"
                onClick={() => fill(example)}
                aria-label={t("exampleLabel", { example })}
                className="h-auto max-w-full py-1.5 text-left font-mono text-sm break-all whitespace-normal"
              >
                {example}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}
