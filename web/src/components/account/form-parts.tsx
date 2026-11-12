import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const INPUT_CLASS =
  "h-12 w-full min-w-0 rounded-[10px] border-2 border-input-border bg-input-bg px-4 text-base text-ink";
export const BUTTON_CLASS =
  "min-h-12 cursor-pointer rounded-[10px] bg-accent px-[22px] font-condensed text-[19px] font-bold tracking-[0.06em] text-on-accent hover:bg-accent-hover disabled:cursor-wait";
export const SECONDARY_BUTTON_CLASS =
  "min-h-11 cursor-pointer rounded-[10px] border-[1.5px] border-btn-border bg-transparent px-3.5 text-ink hover:bg-row-hover";
export const LINK_CLASS = "font-semibold text-accent underline hover:text-accent-hover";

export function AccountCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-[520px] rounded-[18px] bg-panel p-6 sm:p-8">
      <h1 className="font-condensed text-[38px] leading-tight font-bold sm:text-[44px]">{title}</h1>
      <div className="mt-4 flex flex-col gap-4 text-ink2">{children}</div>
    </section>
  );
}

type FieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
};

export function EmailField({ id, label, value, onChange }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[15px] font-semibold text-ink">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type="email"
        value={value}
        required
        autoComplete="email"
        autoCapitalize="off"
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        className={INPUT_CLASS}
      />
    </div>
  );
}

export function FormMessage({ id, tone, children }: { id: string; tone: "error" | "info"; children: ReactNode }) {
  return (
    <p
      id={id}
      role="status"
      aria-live="polite"
      className={cn("min-h-6 font-semibold", tone === "error" && "text-red", tone === "info" && "text-ink")}
    >
      {children}
    </p>
  );
}
