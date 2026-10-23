import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ChapterDanger } from "@/components/home/chapter-danger";
import { ChapterExample } from "@/components/home/chapter-example";
import { ChapterGlossary } from "@/components/home/chapter-glossary";
import { ChapterLimits } from "@/components/home/chapter-limits";
import { ChapterMcp } from "@/components/home/chapter-mcp";
import { ChapterProtect } from "@/components/home/chapter-protect";
import { ChapterRead } from "@/components/home/chapter-read";
import { ChapterStory } from "@/components/home/chapter-story";
import { ChapterUsage } from "@/components/home/chapter-usage";
import { GuideEnd } from "@/components/home/guide-end";
import { GuideOpening } from "@/components/home/guide-opening";
import { ToolZone } from "@/components/home/tool-zone";
import { CONTAINER } from "@/components/page-container";
import { BackToTop } from "@/components/report/back-to-top";
import { EXAMPLE_REPORT } from "@/lib/example-report";
import { cn } from "@/lib/utils";

export async function generateMetadata({ params }: PageProps<"/[locale]">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "home.meta" });
  return { title: t("title"), description: t("description") };
}

export default function HomePage() {
  return (
    <>
      <ToolZone />
      <GuideOpening />
      <div className={cn(CONTAINER, "flex flex-col gap-[72px] pt-16 pb-12")} data-guide="">
        <ChapterMcp />
        <ChapterUsage />
        <ChapterDanger />
        <ChapterStory />
        <ChapterProtect />
        <ChapterRead />
        <ChapterExample report={EXAMPLE_REPORT} />
        <ChapterLimits />
        <ChapterGlossary />
        <GuideEnd />
      </div>
      <BackToTop />
    </>
  );
}
