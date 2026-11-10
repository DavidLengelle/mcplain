"use client";

import type { WidgetMethods } from "altcha/types";
import type {} from "altcha/types/react";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";

import { ALTCHA_CHALLENGE_URL, loadAltcha } from "@/lib/altcha";

export type AltchaHandle = { solve: () => Promise<string | null> };

type Widget = HTMLElement & WidgetMethods;

const READY_WAIT_MS = 3000;
const READY_STEP_MS = 25;

async function readyWidget(element: Widget | null): Promise<Widget | null> {
  const deadline = Date.now() + READY_WAIT_MS;
  while (element !== null && typeof element.verify !== "function") {
    if (Date.now() > deadline) {
      return null;
    }
    await new Promise((resolve) => setTimeout(resolve, READY_STEP_MS));
  }
  return element;
}

export function AltchaField({ ref }: { ref: Ref<AltchaHandle> }) {
  const widget = useRef<Widget>(null);

  useEffect(() => {
    void loadAltcha();
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      solve: async () => {
        try {
          await loadAltcha();
          await customElements.whenDefined("altcha-widget");
          const element = await readyWidget(widget.current);
          if (element === null) {
            return null;
          }
          element.reset();
          const result = await element.verify({ minDuration: 0 });
          if (result === null) {
            return null;
          }
          return result.payload;
        } catch {
          return null;
        }
      },
    }),
    [],
  );

  return (
    <div hidden className="hidden">
      <altcha-widget ref={widget} challenge={ALTCHA_CHALLENGE_URL} display="invisible" auto="off" />
    </div>
  );
}
