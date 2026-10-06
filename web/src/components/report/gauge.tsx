import { useTranslations } from "next-intl";

import type { VerdictColor } from "@/lib/analysis";
import { GAUGE_ANGLES, isColored } from "@/lib/report";
import { cn } from "@/lib/utils";

const ZONES = [
  { color: "green", path: "M20 130 A100 100 0 0 1 67 45.2", stroke: "stroke-green" },
  { color: "orange", path: "M73.05 41.71 A100 100 0 0 1 166.95 41.71", stroke: "stroke-warn" },
  { color: "red", path: "M173 45.2 A100 100 0 0 1 220 130", stroke: "stroke-red" },
] as const;

export function Gauge({ color, word }: { color: VerdictColor; word: string }) {
  const t = useTranslations("verdict");
  let angle: number | null = null;
  if (isColored(color)) {
    angle = GAUGE_ANGLES[color];
  }

  return (
    <div className="flex flex-none flex-col items-center gap-1.5">
      <svg
        viewBox="0 0 240 150"
        width="270"
        height="169"
        role="img"
        aria-label={t("gaugeLabel", { word })}
        data-gauge={color}
        className="h-auto max-w-full"
      >
        {ZONES.map((zone) => (
          <path
            key={zone.color}
            d={zone.path}
            fill="none"
            strokeWidth="18"
            data-zone={zone.color}
            data-active={zone.color === color}
            className={cn(zone.stroke, zone.color === color && "opacity-100", zone.color !== color && "opacity-22")}
          />
        ))}
        {angle !== null && (
          <g transform={`rotate(${angle} 120 130)`} data-needle={angle}>
            <path d="M120 130 L120 46" strokeWidth="5" strokeLinecap="round" className="stroke-needle" />
          </g>
        )}
        {angle !== null && <circle cx="120" cy="130" r="12" className="fill-needle" />}
        {angle !== null && <circle cx="120" cy="130" r="4" className="fill-hub-hole" />}
      </svg>
      <div
        aria-hidden="true"
        className="flex gap-[18px] font-condensed text-sm font-semibold tracking-[0.08em] text-muted"
      >
        <span>{t("zones.green")}</span>
        <span>{t("zones.orange")}</span>
        <span>{t("zones.red")}</span>
      </div>
    </div>
  );
}
