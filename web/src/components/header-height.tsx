"use client";

import { useEffect } from "react";

import { PHONE_QUERY } from "@/lib/phone-mode";

export const HEADER_HEIGHT_VARIABLE = "--header-height";

export function HeaderHeight({ headerId, barId }: { headerId: string; barId: string }) {
  useEffect(() => {
    const header = document.getElementById(headerId);
    const bar = document.getElementById(barId);
    if (header === null || bar === null) {
      return;
    }
    const root = document.documentElement;
    const media = window.matchMedia(PHONE_QUERY);
    const update = () => {
      let stuck = header;
      if (media.matches) {
        stuck = bar;
      }
      root.style.setProperty(HEADER_HEIGHT_VARIABLE, `${Math.ceil(stuck.getBoundingClientRect().height)}px`);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(header);
    observer.observe(bar);
    media.addEventListener("change", update);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", update);
    };
  }, [headerId, barId]);

  return null;
}
