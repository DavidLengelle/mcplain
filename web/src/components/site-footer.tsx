import { useTranslations } from "next-intl";

import { SOURCE_CODE_URL } from "@/lib/constants";

export function SiteFooter() {
  const t = useTranslations("footer");

  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-4 text-sm">
        <span>{t("license")}</span>
        <a
          href={SOURCE_CODE_URL}
          className="rounded-sm underline underline-offset-4 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("sourceCode")}
        </a>
      </div>
    </footer>
  );
}
