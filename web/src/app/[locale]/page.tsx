import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import { AnalysisForm } from "@/components/analysis-form";

export default function HomePage() {
  const t = useTranslations("home");

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("tagline")}</h1>
        <p className="flex items-start gap-2 text-lg">
          <ShieldCheck aria-hidden="true" className="mt-1 size-5 shrink-0" />
          <span>{t("staticAnalysis")}</span>
        </p>
      </div>
      <AnalysisForm />
    </div>
  );
}
