import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

export function ReportSection({ id, title, children }: { id: string; title: ReactNode; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h2 id={id} className="text-2xl font-bold tracking-tight">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[12rem_1fr] sm:gap-3">
      <dt className="font-semibold">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export function Label({ children }: { children: ReactNode }) {
  const t = useTranslations("common");

  return (
    <span className="font-semibold">
      {children}
      {t("colon")}
    </span>
  );
}
