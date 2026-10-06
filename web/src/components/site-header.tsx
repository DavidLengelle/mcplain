import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import { HeaderForm } from "./header-form";
import { HeaderHeight } from "./header-height";
import { LocaleSwitcher } from "./locale-switcher";
import { ThemeSwitcher } from "./theme-switcher";

export const SITE_HEADER_ID = "site-header";

export function SiteHeader() {
  const t = useTranslations("header");

  return (
    <header id={SITE_HEADER_ID} className="sticky top-0 z-20 bg-page shadow-[0_1px_0_var(--line)]">
      <HeaderHeight targetId={SITE_HEADER_ID} />
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" aria-label={t("home")} className="flex min-h-11 items-center gap-2.5 rounded-md text-ink no-underline">
          <span aria-hidden="true" className="size-3.5 rounded-full bg-accent shadow-logo-glow" />
          <span className="font-condensed text-[28px] font-bold tracking-[0.08em]">{t("brand")}</span>
        </Link>
        <HeaderForm />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
          <ThemeSwitcher />
          <LocaleSwitcher />
        </div>
      </div>
    </header>
  );
}
