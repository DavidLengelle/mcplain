import { useTranslations } from "next-intl";

import { SOURCE_CODE_URL } from "@/lib/constants";

export function SiteFooter() {
  const t = useTranslations("footer");

  return (
    <footer className="mx-auto flex w-full max-w-[1180px] flex-wrap items-center justify-between gap-2 border-t border-line px-4 pt-4 pb-12 text-sm text-faint sm:px-6">
      <span>{t("license")}</span>
      <a href={SOURCE_CODE_URL} className="inline-flex min-h-11 items-center text-accent hover:text-accent-hover">
        {t("sourceCode")}
      </a>
    </footer>
  );
}
