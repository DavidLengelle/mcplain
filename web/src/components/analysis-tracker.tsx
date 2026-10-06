"use client";

import { notFound } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Link } from "@/i18n/navigation";
import { isRunning, RUNNING_STATES, type AnalysisView, type RunningState } from "@/lib/analysis";
import { fetchAnalysis } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { CheckIcon, CircleIcon, SpinnerIcon } from "./icons";
import { ReportView } from "./report/report-view";
import { RetryButton } from "./report/retry-button";
import { VerdictFrame } from "./report/verdict-block";

export const POLL_MILLISECONDS = 1000;
export const MAX_WAIT_MILLISECONDS = 3 * 60 * 1000;
export const MAX_FAILURES = 3;

type StepState = "done" | "current" | "waiting";

type TrackerView =
  | { kind: "loading" }
  | { kind: "running"; state: RunningState }
  | { kind: "finished"; analysis: AnalysisView }
  | { kind: "unverified"; last: AnalysisView | null }
  | { kind: "timeout"; last: AnalysisView | null }
  | { kind: "not_found" };

function stepState(step: RunningState, current: RunningState): StepState {
  const stepIndex = RUNNING_STATES.indexOf(step);
  const currentIndex = RUNNING_STATES.indexOf(current);
  if (stepIndex < currentIndex) {
    return "done";
  }
  if (stepIndex === currentIndex) {
    return "current";
  }
  return "waiting";
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return <CheckIcon className="size-6 stroke-green" />;
  }
  if (state === "current") {
    return <SpinnerIcon className="size-6 stroke-accent" />;
  }
  return <CircleIcon className="size-6 stroke-faint" />;
}

function Steps({ current }: { current: RunningState | null }) {
  const t = useTranslations("tracker");
  let announcement = t("loading");
  if (current !== null) {
    announcement = t("current", { step: t(`steps.${current}`) });
  }

  return (
    <section aria-labelledby="tracker-heading" className="flex flex-col gap-5 rounded-[22px] bg-panel px-6 py-7 sm:px-8">
      <h1 id="tracker-heading" className="font-condensed text-[32px] leading-tight font-bold tracking-[0.04em]">
        {t("heading")}
      </h1>
      <ol className="flex flex-col gap-3">
        {RUNNING_STATES.map((step) => {
          let state: StepState = "waiting";
          if (current !== null) {
            state = stepState(step, current);
          }
          return (
            <li
              key={step}
              data-step={step}
              data-state={state}
              className={cn(
                "flex items-center gap-3 text-lg text-ink2",
                state === "current" && "font-semibold text-ink",
              )}
            >
              <StepIcon state={state} />
              <span>{t(`steps.${step}`)}</span>
              <span className="sr-only">({t(`stepState.${state}`)})</span>
            </li>
          );
        })}
      </ol>
      <p aria-live="polite" role="status" className="font-semibold">
        {announcement}
      </p>
      {current === null && (
        <div aria-hidden="true" className="h-24 w-full animate-pulse rounded-2xl bg-panel2 motion-reduce:animate-none" />
      )}
    </section>
  );
}

function GrayState({ kind, last }: { kind: "unverified" | "timeout"; last: AnalysisView | null }) {
  const t = useTranslations("grayStates");

  return (
    <div className="flex flex-col gap-4">
      <VerdictFrame color="gray" title={t(`${kind}.title`)}>
        <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">{t(`${kind}.body`)}</p>
        <p className="mt-3 max-w-[60ch] text-lg font-semibold">{t("notSafe")}</p>
        {last !== null && <RetryButton input={last.input} select={last.select} />}
      </VerdictFrame>
      <p>
        <Link href="/" className="inline-flex min-h-11 items-center font-semibold text-accent underline underline-offset-4">
          {t("home")}
        </Link>
      </p>
    </div>
  );
}

export function AnalysisTracker({ id }: { id: string }) {
  const [view, setView] = useState<TrackerView>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const started = Date.now();
    let active = true;
    let failures = 0;
    let last: AnalysisView | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function schedule() {
      timer = setTimeout(poll, POLL_MILLISECONDS);
    }

    async function poll() {
      if (Date.now() - started > MAX_WAIT_MILLISECONDS) {
        setView({ kind: "timeout", last });
        return;
      }
      const outcome = await fetchAnalysis(id, controller.signal);
      if (!active) {
        return;
      }
      if (outcome.kind === "not_found") {
        setView({ kind: "not_found" });
        return;
      }
      if (outcome.kind === "invalid") {
        setView({ kind: "unverified", last });
        return;
      }
      if (outcome.kind === "unavailable") {
        failures += 1;
        if (failures >= MAX_FAILURES) {
          setView({ kind: "unverified", last });
          return;
        }
        schedule();
        return;
      }
      failures = 0;
      const analysis = outcome.analysis;
      last = analysis;
      if (isRunning(analysis.state)) {
        setView({ kind: "running", state: analysis.state });
        schedule();
        return;
      }
      setView({ kind: "finished", analysis });
    }

    poll();
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [id]);

  if (view.kind === "not_found") {
    notFound();
  }
  if (view.kind === "loading") {
    return <Steps current={null} />;
  }
  if (view.kind === "running") {
    return <Steps current={view.state} />;
  }
  if (view.kind === "unverified" || view.kind === "timeout") {
    return <GrayState kind={view.kind} last={view.last} />;
  }
  return <ReportView analysis={view.analysis} />;
}
