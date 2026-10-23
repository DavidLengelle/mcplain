import { useTranslations } from "next-intl";

import type { VerdictColor } from "@/lib/analysis";
import { GAUGE_ANGLES, isColored } from "@/lib/report";
import { cn } from "@/lib/utils";

const ZONES = [
  { color: "green", path: "M20 130 A100 100 0 0 1 67 45.2", stroke: "stroke-green" },
  { color: "orange", path: "M73.05 41.71 A100 100 0 0 1 166.95 41.71", stroke: "stroke-warn" },
  { color: "red", path: "M173 45.2 A100 100 0 0 1 220 130", stroke: "stroke-red" },
] as const;

export type GaugeSize = "full" | "compact" | "small";

const SIZES: Record<GaugeSize, { width: number; height: number; zone: number; needle: number; hub: number; hole: number }> = {
  full: { width: 270, height: 169, zone: 18, needle: 5, hub: 12, hole: 4 },
  compact: { width: 240, height: 150, zone: 18, needle: 5, hub: 12, hole: 4 },
  small: { width: 132, height: 83, zone: 20, needle: 7, hub: 13, hole: 5 },
};

export function Gauge({ color, word, size = "full" }: { color: VerdictColor; word: string; size?: GaugeSize }) {
  const t = useTranslations("verdict");
  const shape = SIZES[size];
  let angle: number | null = null;
  if (isColored(color)) {
    angle = GAUGE_ANGLES[color];
  }

  return (
    <div className={cn("flex flex-none flex-col gap-1.5", size !== "small" && "items-center")}>
      <svg
        viewBox="0 0 240 150"
        width={shape.width}
        height={shape.height}
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
            strokeWidth={shape.zone}
            data-zone={zone.color}
            data-active={zone.color === color}
            className={cn(zone.stroke, zone.color === color && "opacity-100", zone.color !== color && "opacity-22")}
          />
        ))}
        {angle !== null && (
          <g transform={`rotate(${angle} 120 130)`} data-needle={angle}>
            <path d="M120 130 L120 46" strokeWidth={shape.needle} strokeLinecap="round" className="stroke-needle" />
          </g>
        )}
        {angle !== null && <circle cx="120" cy="130" r={shape.hub} className="fill-needle" />}
        {angle !== null && <circle cx="120" cy="130" r={shape.hole} className="fill-hub-hole" />}
      </svg>
      {size !== "small" && (
        <div
          aria-hidden="true"
          className="flex gap-[18px] font-condensed text-sm font-semibold tracking-[0.08em] text-muted"
        >
          <span>{t("zones.green")}</span>
          <span>{t("zones.orange")}</span>
          <span>{t("zones.red")}</span>
        </div>
      )}
    </div>
  );
}
