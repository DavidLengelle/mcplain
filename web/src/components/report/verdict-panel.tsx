import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { VerdictColor } from "@/lib/analysis";
import { cn } from "@/lib/utils";
import { VERDICT_STYLES } from "@/lib/verdict-style";

import { EngineText } from "../engine-text";
import { VerdictBadge } from "../verdict-badge";

type VerdictPanelProps = {
  color: VerdictColor;
  alertCount?: number;
  reasons?: string[];
  contactedDomains?: string[];
  children?: ReactNode;
};

export function VerdictPanel({ color, alertCount = 0, reasons = [], contactedDomains = [], children }: VerdictPanelProps) {
  const t = useTranslations("verdict");

  return (
    <section
      aria-labelledby="verdict-heading"
      data-verdict-panel={color}
      className={cn("flex flex-col gap-3 rounded-lg border-2 border-l-8 p-5", VERDICT_STYLES[color].panel)}
    >
      <h2 id="verdict-heading" className="text-sm font-semibold tracking-wide uppercase">
        {t("heading")}
      </h2>
      <div className="flex flex-wrap items-center gap-3">
        <VerdictBadge color={color} size="large" />
        <p className="text-lg font-semibold">{t(`${color}.summary`)}</p>
      </div>
      {color === "gray" && <p className="text-lg font-bold">{t("notSafe")}</p>}
      {alertCount > 0 && <p className="font-semibold">{t("alertCount", { count: alertCount })}</p>}
      {children}
      {reasons.length > 0 && (
        <div>
          <h3 className="font-semibold">{t("reasons")}</h3>
          <ul className="mt-1 list-disc pl-6">
            {reasons.map((reason) => (
              <li key={reason}>
                <EngineText code={`reason.${reason}`} params={{ domains: contactedDomains.join(", ") }} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-sm">
        <EngineText code="cli.verdict.disclaimer" />
      </p>
    </section>
  );
}
