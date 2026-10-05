import { useTranslations } from "next-intl";

import type { StartOutcome } from "@/lib/api-client";

import { EngineText } from "./engine-text";

export type StartError = Exclude<StartOutcome, { kind: "accepted" }> | { kind: "empty" };

export function StartErrorText({ error }: { error: StartError }) {
  const t = useTranslations("form");
  if (error.kind === "invalid") {
    return <EngineText code={error.code} params={error.params} />;
  }
  return <>{t(error.kind)}</>;
}
