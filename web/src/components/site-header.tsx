import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import { LocaleSwitcher } from "./locale-switcher";

export function SiteHeader() {
  const t = useTranslations("header");

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4 px-4 py-3">
        <Link
          href="/"
          aria-label={t("home")}
          className="rounded-md text-xl font-bold tracking-tight focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("brand")}
        </Link>
        <LocaleSwitcher />
      </div>
    </header>
  );
}
