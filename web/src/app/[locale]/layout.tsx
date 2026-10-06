import type { Metadata } from "next";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import Script from "next/script";
import { connection } from "next/server";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";

import { EngineNotice } from "@/components/engine-notice";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { routing } from "@/i18n/routing";
import { TOP_ID } from "@/lib/constants";
import { NONCE_HEADER } from "@/lib/security-headers";
import { THEME_SCRIPT_PATH } from "@/lib/theme";

import { plexMono, saira, sairaCondensed } from "../fonts";
import "../globals.css";

export async function generateMetadata({ params }: LayoutProps<"/[locale]">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata" });
  return { title: t("title"), description: t("description") };
}

export default async function LocaleLayout({ children, params }: LayoutProps<"/[locale]">) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }
  await connection();
  const nonce = (await headers()).get(NONCE_HEADER) ?? undefined;
  const messages = await getMessages();
  const engineAvailable = Object.keys(messages.engine ?? {}).length > 0;
  const t = await getTranslations("a11y");

  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${saira.variable} ${sairaCondensed.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-page text-ink">
        <Script src={THEME_SCRIPT_PATH} strategy="beforeInteractive" nonce={nonce} />
        <NextIntlClientProvider>
          <div id={TOP_ID} />
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-page"
          >
            {t("skipToContent")}
          </a>
          <SiteHeader />
          {!engineAvailable && <EngineNotice />}
          <main id="main" className="mx-auto w-full max-w-[1180px] flex-1 px-4 pt-8 pb-10 sm:px-6">
            {children}
          </main>
          <SiteFooter />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
