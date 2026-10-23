"use client";

import type { MouseEvent, ReactNode } from "react";

import { TOOL_ZONE_ID } from "@/lib/constants";

import { HOME_INPUT_ID } from "../analysis-field";

const MAIN_BUTTON = 0;

function opensElsewhere(event: MouseEvent<HTMLAnchorElement>): boolean {
  return event.button !== MAIN_BUTTON || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

export function AnalyzeLink({ className, children }: { className: string; children: ReactNode }) {
  function goToField(event: MouseEvent<HTMLAnchorElement>) {
    const zone = document.getElementById(TOOL_ZONE_ID);
    const field = document.getElementById(HOME_INPUT_ID);
    if (zone === null || field === null || opensElsewhere(event)) {
      return;
    }
    event.preventDefault();
    zone.scrollIntoView({ block: "start" });
    field.focus({ preventScroll: true });
    window.history.pushState(null, "", `#${TOOL_ZONE_ID}`);
  }

  return (
    <a href={`#${TOOL_ZONE_ID}`} onClick={goToField} className={className} data-analyze-link="">
      {children}
    </a>
  );
}
