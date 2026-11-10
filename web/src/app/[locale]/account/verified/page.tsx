import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AccountCard, LINK_CLASS } from "@/components/account/form-parts";
import { PageContainer } from "@/components/page-container";
import { Link } from "@/i18n/navigation";

export async function generateMetadata({ params }: PageProps<"/[locale]/account/verified">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("verified.metaTitle"), robots: { index: false } };
}

export default async function Page({ params, searchParams }: PageProps<"/[locale]/account/verified">) {
  const { locale } = await params;
  const query = await searchParams;
  const t = await getTranslations({ locale, namespace: "account" });
  if (query.error !== undefined) {
    return (
      <PageContainer>
        <AccountCard title={t("verified.errorTitle")}>
          <p data-testid="verified-error">{t("verified.error")}</p>
          <p>
            <Link href="/account/sign-in" className={LINK_CLASS}>
              {t("verified.signInLink")}
            </Link>
          </p>
        </AccountCard>
      </PageContainer>
    );
  }
  return (
    <PageContainer>
      <AccountCard title={t("verified.okTitle")}>
        <p data-testid="verified-ok">{t("verified.ok")}</p>
        <p>
          <Link href="/account" className={LINK_CLASS}>
            {t("common.backToAccount")}
          </Link>
        </p>
      </AccountCard>
    </PageContainer>
  );
}
