"use client";

import { useEffect } from "react";

export const HEADER_HEIGHT_VARIABLE = "--header-height";

export function HeaderHeight({ targetId }: { targetId: string }) {
  useEffect(() => {
    const header = document.getElementById(targetId);
    if (header === null) {
      return;
    }
    const root = document.documentElement;
    const update = () => root.style.setProperty(HEADER_HEIGHT_VARIABLE, `${Math.ceil(header.getBoundingClientRect().height)}px`);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(header);
    return () => observer.disconnect();
  }, [targetId]);

  return null;
}
