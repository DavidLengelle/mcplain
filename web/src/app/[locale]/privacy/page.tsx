import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PageContainer } from "@/components/page-container";

const SECTIONS = ["visits", "cookie", "address", "email"] as const;
const PARAGRAPHS: Record<(typeof SECTIONS)[number], readonly string[]> = {
  visits: ["what", "counted", "notCounted", "signals"],
  cookie: ["session", "theme"],
  address: ["fingerprint", "salt"],
  email: ["links", "deletion"],
};

export async function generateMetadata({ params }: PageProps<"/[locale]/privacy">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "privacy" });
  return { title: t("metaTitle") };
}

export default async function PrivacyPage() {
  const t = await getTranslations("privacy");
  return (
    <PageContainer>
      <article className="mx-auto flex w-full max-w-[760px] flex-col gap-6" data-privacy="">
        <h1 className="font-condensed text-[38px] leading-tight font-bold sm:text-[44px]">{t("title")}</h1>
        <p className="text-lg text-ink2">{t("intro")}</p>
        {SECTIONS.map((section) => (
          <section key={section} aria-labelledby={`privacy-${section}`} className="flex flex-col gap-3 rounded-[18px] bg-panel p-5 sm:p-6">
            <h2 id={`privacy-${section}`} className="font-condensed text-[28px] leading-tight font-bold">
              {t(`${section}.title`)}
            </h2>
            {PARAGRAPHS[section].map((paragraph) => (
              <p key={paragraph} className="max-w-[68ch] leading-[1.6] text-ink2">
                {t(`${section}.${paragraph}`)}
              </p>
            ))}
          </section>
        ))}
      </article>
    </PageContainer>
  );
}
