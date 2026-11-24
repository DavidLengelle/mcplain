"use client";

import { useTranslations } from "next-intl";

import type { ActionOutcome } from "@/lib/admin-dashboard";

const API_PREFIX = "api.";

export function useOutcomeText(): (outcome: ActionOutcome) => string {
  const t = useTranslations("admin.dashboard.outcome");
  return (outcome: ActionOutcome) => {
    if (outcome.kind === "done") {
      return t("done");
    }
    if (outcome.kind === "refused") {
      const key = outcome.code.replace(API_PREFIX, "");
      if (t.has(key)) {
        return t(key);
      }
    }
    return t("failed");
  };
}
