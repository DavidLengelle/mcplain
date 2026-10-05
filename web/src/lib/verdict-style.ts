import { CircleCheck, CircleHelp, OctagonX, TriangleAlert, type LucideIcon } from "lucide-react";

import type { VerdictColor } from "./analysis";

export type VerdictStyle = { icon: LucideIcon; chip: string; panel: string };

export const VERDICT_STYLES: Record<VerdictColor, VerdictStyle> = {
  red: {
    icon: OctagonX,
    chip: "bg-red-700 text-white",
    panel: "border-red-700 bg-red-50 dark:border-red-400 dark:bg-red-950",
  },
  orange: {
    icon: TriangleAlert,
    chip: "bg-orange-700 text-white",
    panel: "border-orange-700 bg-orange-50 dark:border-orange-400 dark:bg-orange-950",
  },
  green: {
    icon: CircleCheck,
    chip: "bg-green-700 text-white",
    panel: "border-green-700 bg-green-50 dark:border-green-400 dark:bg-green-950",
  },
  gray: {
    icon: CircleHelp,
    chip: "bg-zinc-700 text-white",
    panel: "border-zinc-600 bg-zinc-100 dark:border-zinc-400 dark:bg-zinc-900",
  },
};
