"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

export function LocaleSwitcher() {
  const t = useTranslations("localeSwitcher");
  const current = useLocale();
  const pathname = usePathname();

  return (
    <nav aria-label={t("label")}>
      <ul className="flex gap-0.5 rounded-[10px] bg-toggle-bg p-[3px]">
        {routing.locales.map((locale) => (
          <li key={locale}>
            <Link
              href={pathname}
              locale={locale}
              hrefLang={locale}
              aria-current={locale === current}
              className={cn(
                "flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold text-toggle-fg no-underline",
                locale === current && "bg-toggle-on-bg text-toggle-on-fg",
              )}
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
