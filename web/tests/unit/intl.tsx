import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import { engineCatalogToMessages, type MessageTree } from "@/lib/icu";

import english from "../../messages/en.json";
import french from "../../messages/fr.json";

const INTERFACE: Record<string, MessageTree> = { en: english, fr: french };

export function engineTree(locale: string): MessageTree {
  const path = join(process.cwd(), "..", "engine", "src", "mcplain", "locales", `${locale}.json`);
  return engineCatalogToMessages(JSON.parse(readFileSync(path, "utf-8"))) ?? {};
}

export function renderWithIntl(ui: ReactElement, locale = "en", engine: MessageTree = engineTree(locale)) {
  const messages = { ...INTERFACE[locale], engine };
  return render(
    <NextIntlClientProvider locale={locale} messages={messages} timeZone="UTC">
      {ui}
    </NextIntlClientProvider>,
  );
}
