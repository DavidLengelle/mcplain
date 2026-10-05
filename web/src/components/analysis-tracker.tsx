"use client";

import { Check, Circle, LoaderCircle } from "lucide-react";
import { notFound } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { isRunning, RUNNING_STATES, type AnalysisView, type RunningState } from "@/lib/analysis";
import { fetchAnalysis } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { GrayState } from "./report/gray-state";
import { ReportView } from "./report/report-view";

export const POLL_MILLISECONDS = 1000;
export const MAX_WAIT_MILLISECONDS = 3 * 60 * 1000;
export const MAX_FAILURES = 3;

type TrackerView =
  | { kind: "loading" }
  | { kind: "running"; state: RunningState }
  | { kind: "finished"; analysis: AnalysisView }
  | { kind: "unverified" }
  | { kind: "timeout" }
  | { kind: "not_found" };

function stepState(step: RunningState, current: RunningState): "done" | "current" | "waiting" {
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

function StepIcon({ state }: { state: "done" | "current" | "waiting" }) {
  if (state === "done") {
    return <Check aria-hidden="true" className="size-5" />;
  }
  if (state === "current") {
    return <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />;
  }
  return <Circle aria-hidden="true" className="size-5" />;
}

function Steps({ current }: { current: RunningState | null }) {
  const t = useTranslations("tracker");
  let announcement = t("loading");
  if (current !== null) {
    announcement = t("current", { step: t(`steps.${current}`) });
  }

  return (
    <section aria-labelledby="tracker-heading" className="flex flex-col gap-4">
      <h1 id="tracker-heading" className="text-3xl font-bold tracking-tight">
        {t("heading")}
      </h1>
      <ol className="flex flex-col gap-2">
        {RUNNING_STATES.map((step) => {
          let state: "done" | "current" | "waiting" = "waiting";
          if (current !== null) {
            state = stepState(step, current);
          }
          return (
            <li
              key={step}
              data-step={step}
              data-state={state}
              className={cn("flex items-center gap-2 text-lg", state === "current" && "font-bold")}
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
        <div className="flex flex-col gap-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-6 w-2/3" />
        </div>
      )}
    </section>
  );
}

export function AnalysisTracker({ id }: { id: string }) {
  const [view, setView] = useState<TrackerView>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const started = Date.now();
    let active = true;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function schedule() {
      timer = setTimeout(poll, POLL_MILLISECONDS);
    }

    async function poll() {
      if (Date.now() - started > MAX_WAIT_MILLISECONDS) {
        setView({ kind: "timeout" });
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
        setView({ kind: "unverified" });
        return;
      }
      if (outcome.kind === "unavailable") {
        failures += 1;
        if (failures >= MAX_FAILURES) {
          setView({ kind: "unverified" });
          return;
        }
        schedule();
        return;
      }
      failures = 0;
      const analysis = outcome.analysis;
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
    return <GrayState kind={view.kind} />;
  }
  return <ReportView analysis={view.analysis} />;
}
