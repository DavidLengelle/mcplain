import { useTranslations } from "next-intl";

import { AnalysisForm } from "@/components/analysis-form";
import { ShieldIcon } from "@/components/icons";

export default function HomePage() {
  const t = useTranslations("home");

  return (
    <div className="flex max-w-4xl flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h1 className="font-condensed text-4xl font-bold tracking-[0.02em] sm:text-5xl">{t("tagline")}</h1>
        <p className="flex items-start gap-2 text-lg text-ink2">
          <ShieldIcon className="mt-1 size-5 shrink-0 stroke-accent" />
          <span>{t("staticAnalysis")}</span>
        </p>
      </div>
      <AnalysisForm />
    </div>
  );
}
