import { useTranslations } from "next-intl";

import { PageContainer } from "@/components/page-container";
import { Link } from "@/i18n/navigation";

export default function NotFoundPage() {
  const t = useTranslations("notFound");

  return (
    <PageContainer>
      <section data-not-found="" className="flex flex-col items-start gap-4 rounded-[22px] bg-panel px-6 py-7 sm:px-8">
        <h1 className="font-condensed text-[38px] leading-tight font-bold sm:text-[44px]">{t("title")}</h1>
        <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">{t("body")}</p>
        <Link
          href="/"
          className="inline-flex min-h-11 items-center font-semibold text-accent underline underline-offset-4 hover:text-accent-hover"
        >
          {t("home")}
        </Link>
      </section>
    </PageContainer>
  );
}
