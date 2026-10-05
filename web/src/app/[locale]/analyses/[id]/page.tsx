import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AnalysisTracker } from "@/components/analysis-tracker";
import { isAnalysisId } from "@/lib/api-client";

export async function generateMetadata({ params }: PageProps<"/[locale]/analyses/[id]">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata" });
  return { title: t("analysisTitle") };
}

export default async function AnalysisPage({ params }: PageProps<"/[locale]/analyses/[id]">) {
  const { id } = await params;
  if (!isAnalysisId(id)) {
    notFound();
  }
  return <AnalysisTracker key={id} id={id} />;
}
