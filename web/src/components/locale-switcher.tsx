"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

export function LocaleSwitcher() {
  const t = useTranslations("localeSwitcher");
  const current = useLocale();
  const pathname = usePathname();

  return (
    <nav aria-label={t("label")}>
      <ul className="flex items-center gap-1 text-sm font-semibold">
        {routing.locales.map((locale, index) => (
          <li key={locale} className="flex items-center gap-1">
            {index > 0 && (
              <span aria-hidden="true" className="text-muted-foreground">
                |
              </span>
            )}
            <Link
              href={pathname}
              locale={locale}
              hrefLang={locale}
              aria-current={locale === current}
              className="rounded-md px-2 py-1 underline-offset-4 hover:underline aria-[current=true]:bg-foreground aria-[current=true]:text-background focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {t(`short.${locale}`)}
              <span className="sr-only" lang={locale}>
                {" "}
                {t(`name.${locale}`)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
