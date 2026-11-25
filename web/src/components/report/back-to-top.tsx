"use client";

import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";

import { TOP_ID } from "@/lib/constants";

import { ArrowUpIcon } from "../icons";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("scroll", onChange, { passive: true });
  window.addEventListener("resize", onChange);
  return () => {
    window.removeEventListener("scroll", onChange);
    window.removeEventListener("resize", onChange);
  };
}

function pastFirstScreen(): boolean {
  return window.scrollY >= window.innerHeight;
}

function onServer(): boolean {
  return false;
}

export function BackToTop() {
  const t = useTranslations("report");
  const shown = useSyncExternalStore(subscribe, pastFirstScreen, onServer);

  if (!shown) {
    return null;
  }
  return (
    <a
      href={`#${TOP_ID}`}
      aria-label={t("backToTop")}
      data-back-to-top=""
      className="fixed right-3 bottom-3 z-30 flex size-12 items-center justify-center rounded-full bg-accent no-underline shadow-arrow"
    >
      <ArrowUpIcon className="size-6 stroke-on-accent" />
    </a>
  );
}
