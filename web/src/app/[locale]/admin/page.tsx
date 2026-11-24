import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AdminPanel } from "@/components/admin/admin-panel";
import { PageContainer } from "@/components/page-container";

export async function generateMetadata({ params }: PageProps<"/[locale]/admin">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("metaTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <PageContainer>
      <AdminPanel />
    </PageContainer>
  );
}
