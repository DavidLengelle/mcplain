import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import { AccountMenu } from "./account/account-menu";
import { HeaderField } from "./header-field";
import { HeaderHeight } from "./header-height";
import { LocaleSwitcher } from "./locale-switcher";
import { PHONE_BAR_ID, PhoneBar } from "./phone-bar";
import { QuotaCounter } from "./quota-counter";
import { ThemeSwitcher } from "./theme-switcher";

export const SITE_HEADER_ID = "site-header";

export function SiteHeader() {
  const t = useTranslations("header");

  return (
    <header
      id={SITE_HEADER_ID}
      data-header-stuck=""
      className="z-20 bg-page shadow-[0_1px_0_var(--line)] desk:sticky desk:top-0"
    >
      <HeaderHeight headerId={SITE_HEADER_ID} barId={PHONE_BAR_ID} />
      <PhoneBar />
      <div aria-hidden="true" className="h-16 desk:hidden" />
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-x-6 gap-y-3 desk:px-6 desk:py-3">
        <Link
          href="/"
          aria-label={t("home")}
          className="flex min-h-11 items-center gap-2.5 rounded-md text-ink no-underline phone:hidden"
        >
          <span aria-hidden="true" className="size-3.5 rounded-full bg-accent shadow-logo-glow" />
          <span className="font-condensed text-[28px] font-bold tracking-[0.08em]">{t("brand")}</span>
        </Link>
        <HeaderField />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 phone:hidden">
          <ThemeSwitcher />
          <LocaleSwitcher />
          <AccountMenu />
        </div>
      </div>
      <QuotaCounter />
    </header>
  );
}
