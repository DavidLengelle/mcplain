import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SignInForm } from "@/components/account/sign-in-form";
import { PageContainer } from "@/components/page-container";

export async function generateMetadata({ params }: PageProps<"/[locale]/account/sign-in">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("signIn.metaTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <PageContainer>
      <SignInForm />
    </PageContainer>
  );
}
