"use client";

import { useLocale, useTranslations } from "next-intl";

import { getPathname, Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

const ITEM_CLASS = "flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold no-underline";
const CURRENT_CLASS = "bg-toggle-on-bg text-toggle-on-fg";
const OTHER_CLASS = "text-toggle-fg";

function LocaleLabel({ locale }: { locale: string }) {
  const t = useTranslations("localeSwitcher");
  return (
    <>
      {t(`short.${locale}`)}
      <span className="sr-only" lang={locale}>
        {" "}
        {t(`name.${locale}`)}
      </span>
    </>
  );
}

export function LocaleSwitcher() {
  const t = useTranslations("localeSwitcher");
  const current = useLocale();
  const pathname = usePathname();

  return (
    <nav aria-label={t("label")}>
      <ul className="flex gap-0.5 rounded-[10px] bg-toggle-bg p-[3px]">
        {routing.locales.map((locale) => (
          <li key={locale}>
            {locale === current && (
              <Link
                href={pathname}
                prefetch={false}
                hrefLang={locale}
                aria-current={true}
                data-locale-link={locale}
                className={cn(ITEM_CLASS, CURRENT_CLASS)}
              >
                <LocaleLabel locale={locale} />
              </Link>
            )}
            {locale !== current && (
              <a
                href={getPathname({ href: pathname, locale, forcePrefix: true })}
                hrefLang={locale}
                aria-current={false}
                data-locale-link={locale}
                className={cn(ITEM_CLASS, OTHER_CLASS)}
              >
                <LocaleLabel locale={locale} />
              </a>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
