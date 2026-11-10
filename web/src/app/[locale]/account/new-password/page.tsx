import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NewPasswordForm } from "@/components/account/new-password-form";
import { PageContainer } from "@/components/page-container";

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{8,256}$/;

export async function generateMetadata({ params }: PageProps<"/[locale]/account/new-password">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("newPassword.metaTitle"), robots: { index: false } };
}

function readToken(value: string | string[] | undefined): string | null {
  if (typeof value !== "string" || !TOKEN_PATTERN.test(value)) {
    return null;
  }
  return value;
}

export default async function Page({ searchParams }: PageProps<"/[locale]/account/new-password">) {
  const query = await searchParams;
  let token = readToken(query.token);
  if (query.error !== undefined) {
    token = null;
  }
  return (
    <PageContainer>
      <NewPasswordForm token={token} />
    </PageContainer>
  );
}
