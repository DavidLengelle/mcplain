"use client";

import { useTranslations } from "next-intl";
import { useEffect, useSyncExternalStore } from "react";

import {
  applyThemeClass,
  chooseTheme,
  readThemeChoice,
  subscribeToTheme,
  THEME_CHOICES,
  type ThemeChoice,
} from "@/lib/theme";
import { cn } from "@/lib/utils";

function serverChoice(): ThemeChoice {
  return "system";
}

export function ThemeSwitcher() {
  const t = useTranslations("theme");
  const choice = useSyncExternalStore(subscribeToTheme, readThemeChoice, serverChoice);

  useEffect(() => {
    applyThemeClass(document.documentElement, readThemeChoice());
  }, []);

  return (
    <div role="group" aria-label={t("label")} className="flex gap-0.5 rounded-[10px] bg-toggle-bg p-[3px]">
      {THEME_CHOICES.map((item) => (
        <button
          key={item}
          type="button"
          aria-pressed={item === choice}
          data-theme-choice={item}
          onClick={() => chooseTheme(item)}
          className={cn(
            "min-h-11 cursor-pointer rounded-lg px-3 text-sm font-medium text-toggle-fg",
            item === choice && "bg-toggle-on-bg text-toggle-on-fg",
          )}
        >
          {t(item)}
        </button>
      ))}
    </div>
  );
}
