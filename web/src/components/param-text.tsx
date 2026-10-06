import { useTranslations } from "next-intl";
import { Fragment, type ReactNode } from "react";

import { MESSAGE_KEY_PATTERN } from "@/lib/analysis";

import { RawText } from "./raw-text";

export type TextParams = Record<string, string | number>;

const MARK_START = "";
const MARK_END = "";
const MARK_PATTERN = /(\d+)/;
const FIELD_PATTERN = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
const PLAIN_NUMBER = /^\d+$/;

function ParamValue({ value }: { value: string | number | undefined }) {
  if (value === undefined) {
    return <>?</>;
  }
  const text = String(value);
  if (PLAIN_NUMBER.test(text)) {
    return <>{text}</>;
  }
  return <RawText value={text} limit={200} />;
}

export function withRawParams(
  template: string,
  format: (markers: Record<string, string>) => string,
  params: TextParams,
): ReactNode {
  const names = Array.from(new Set(Array.from(template.matchAll(FIELD_PATTERN), (match) => match[1])));
  const markers: Record<string, string> = {};
  names.forEach((name, index) => {
    markers[name] = `${MARK_START}${index}${MARK_END}`;
  });
  const parts = format(markers).split(MARK_PATTERN);
  return parts.map((part, index) => {
    if (index % 2 === 0) {
      return <Fragment key={index}>{part}</Fragment>;
    }
    return <ParamValue key={index} value={params[names[Number(part)]]} />;
  });
}

export function InterfaceText({ code, params = {} }: { code: string; params?: TextParams }) {
  const t = useTranslations();
  if (!MESSAGE_KEY_PATTERN.test(code) || !t.has(code as never)) {
    return null;
  }
  const raw: unknown = t.raw(code as never);
  if (typeof raw !== "string") {
    return null;
  }
  return <>{withRawParams(raw, (markers) => t(code as never, markers as never), params)}</>;
}
