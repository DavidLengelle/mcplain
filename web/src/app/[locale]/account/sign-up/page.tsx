import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SignUpForm } from "@/components/account/sign-up-form";
import { PageContainer } from "@/components/page-container";

export async function generateMetadata({ params }: PageProps<"/[locale]/account/sign-up">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("signUp.metaTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <PageContainer>
      <SignUpForm />
    </PageContainer>
  );
}
