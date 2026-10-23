"use client";

import { usePathname } from "@/i18n/navigation";

import { AnalysisField } from "./analysis-field";

export const HOME_PATH = "/";

export function HeaderField() {
  const pathname = usePathname();
  if (pathname === HOME_PATH) {
    return null;
  }
  return <AnalysisField variant="header" />;
}
