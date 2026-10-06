"use client";

import { useState } from "react";

import { useRouter } from "@/i18n/navigation";
import { INPUT_MAX_CHARACTERS, startAnalysis } from "@/lib/api-client";

import type { StartError } from "./start-error";

export type AnalysisStart = {
  pending: boolean;
  error: StartError | null;
  start: (text: string, select?: string | null) => Promise<boolean>;
  clearError: () => void;
};

export function useAnalysisStart(): AnalysisStart {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<StartError | null>(null);

  async function start(text: string, select: string | null = null): Promise<boolean> {
    const input = text.trim().slice(0, INPUT_MAX_CHARACTERS);
    if (input === "") {
      setError({ kind: "empty" });
      return false;
    }
    setPending(true);
    setError(null);
    const outcome = await startAnalysis(input, select);
    if (outcome.kind === "accepted") {
      router.push(`/analyses/${outcome.id}`);
      return true;
    }
    setPending(false);
    setError(outcome);
    return false;
  }

  return { pending, error, start, clearError: () => setError(null) };
}
