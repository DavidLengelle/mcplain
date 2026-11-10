import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ForgotPasswordForm } from "@/components/account/forgot-password-form";
import { PageContainer } from "@/components/page-container";

export async function generateMetadata({ params }: PageProps<"/[locale]/account/forgot-password">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("forgot.metaTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <PageContainer>
      <ForgotPasswordForm />
    </PageContainer>
  );
}
