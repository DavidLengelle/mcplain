import { notFound } from "next/navigation";
import * as rootParams from "next/root-params";
import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { engineMessages } from "@/lib/engine-messages";

import { routing } from "./routing";

export const TIME_ZONE = "UTC";

export default getRequestConfig(async ({ locale }) => {
  let current = locale;
  if (!current) {
    const value = await rootParams.locale();
    if (!hasLocale(routing.locales, value)) {
      notFound();
    }
    current = value;
  }
  const interfaceMessages = (await import(`../../messages/${current}.json`)).default;
  const engine = await engineMessages(current);
  return {
    locale: current,
    timeZone: TIME_ZONE,
    messages: { ...interfaceMessages, engine: engine ?? {} },
  };
});
