import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AccountPanel } from "@/components/account/account-panel";
import { PageContainer } from "@/components/page-container";

export async function generateMetadata({ params }: PageProps<"/[locale]/account">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("page.metaTitle"), robots: { index: false } };
}

export default async function AccountPage({ searchParams }: PageProps<"/[locale]/account">) {
  const query = await searchParams;
  return (
    <PageContainer>
      <AccountPanel linkFailed={query.error !== undefined} />
    </PageContainer>
  );
}
