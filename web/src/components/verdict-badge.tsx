import { useTranslations } from "next-intl";

import type { VerdictColor } from "@/lib/analysis";
import { cn } from "@/lib/utils";
import { VERDICT_STYLES } from "@/lib/verdict-style";

type VerdictBadgeProps = { color: VerdictColor; size?: "default" | "large" };

export function VerdictBadge({ color, size = "default" }: VerdictBadgeProps) {
  const t = useTranslations("verdict");
  const style = VERDICT_STYLES[color];
  const Icon = style.icon;

  return (
    <span
      data-verdict={color}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md font-bold uppercase tracking-wide",
        style.chip,
        size === "default" && "px-2 py-0.5 text-sm",
        size === "large" && "px-3 py-1.5 text-2xl",
      )}
    >
      <Icon aria-hidden="true" className={cn(size === "default" && "size-4", size === "large" && "size-7")} />
      {t(`${color}.word`)}
    </span>
  );
}
