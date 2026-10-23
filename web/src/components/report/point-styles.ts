import type { Alert } from "@/lib/analysis";

export type PointColor = "red" | "orange";

export const DOT: Record<PointColor, string> = {
  red: "bg-red shadow-[0_0_10px_var(--red-glow)]",
  orange: "bg-warn shadow-[0_0_10px_var(--warn-glow)]",
};

export const BADGE: Record<PointColor, string> = {
  red: "border-red bg-transparent text-red",
  orange: "border-warn bg-warn-badge-bg text-warn-text",
};

export function pointColor(alert: Alert): PointColor {
  if (alert.color === "red") {
    return "red";
  }
  return "orange";
}
