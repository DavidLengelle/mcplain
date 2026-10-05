import { notFound } from "next/navigation";
import * as rootParams from "next/root-params";
import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { engineMessages } from "@/lib/engine-messages";

import { routing } from "./routing";

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
    messages: { ...interfaceMessages, engine: engine ?? {} },
  };
});
