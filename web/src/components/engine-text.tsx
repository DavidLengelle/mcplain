import { useTranslations } from "next-intl";

import { MESSAGE_KEY_PATTERN } from "@/lib/analysis";

import { withRawParams, type TextParams } from "./param-text";

export type EngineParams = TextParams;

export function useEngineString(): (code: string) => string {
  const t = useTranslations("engine");
  const fallback = useTranslations("engineText");
  return (code: string) => {
    if (!MESSAGE_KEY_PATTERN.test(code) || !t.has(code as never)) {
      return fallback("unavailable");
    }
    const raw: unknown = t.raw(code as never);
    if (typeof raw !== "string") {
      return fallback("unavailable");
    }
    return t(code as never);
  };
}

export function EngineText({ code, params = {} }: { code: string; params?: EngineParams }) {
  const t = useTranslations("engine");
  const fallback = useTranslations("engineText");
  if (!MESSAGE_KEY_PATTERN.test(code) || !t.has(code as never)) {
    return <>{fallback("unavailable")}</>;
  }
  const raw: unknown = t.raw(code as never);
  if (typeof raw !== "string") {
    return <>{fallback("unavailable")}</>;
  }
  return <>{withRawParams(raw, (markers) => t(code as never, markers as never), params)}</>;
}
