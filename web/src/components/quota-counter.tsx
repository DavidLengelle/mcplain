"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import type { QuotaInfo } from "@/lib/quota";
import { cn } from "@/lib/utils";

import { useVisitor } from "./visitor-context";

export function useResetTime(): (iso: string) => string {
  const locale = useLocale();
  return (iso: string) => new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

function boxState(index: number, left: number): "left" | "used" {
  if (index < left) {
    return "left";
  }
  return "used";
}

function Boxes({ limit, used }: { limit: number; used: number }) {
  const left = limit - used;
  return (
    <span aria-hidden="true" className="flex gap-1">
      {Array.from({ length: limit }, (_, index) => (
        <span
          key={index}
          data-box={boxState(index, left)}
          className={cn("size-2.5 rounded-[3px]", index < left && "bg-accent", index >= left && "bg-counter-off")}
        />
      ))}
    </span>
  );
}

export function QuotaLine({ quota }: { quota: QuotaInfo }) {
  const t = useTranslations("quota");
  const resetTime = useResetTime();

  if (quota.kind === "admin" || quota.kind === "bench") {
    return (
      <p data-testid="quota-counter" data-kind={quota.kind} className="text-sm font-semibold text-ink">
        {t(quota.kind)}
      </p>
    );
  }
  const limit = quota.limit ?? 0;
  const remaining = quota.remaining ?? 0;
  return (
    <div data-testid="quota-counter" data-kind={quota.kind} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <Boxes limit={limit} used={limit - remaining} />
      <span className="font-semibold text-ink">{t("remaining", { count: remaining })}</span>
      {quota.used > 0 && <span className="text-muted">{t("resets", { time: resetTime(quota.resetsAt) })}</span>}
      {quota.kind === "anonymous" && (
        <Link
          href="/account/sign-up"
          data-testid="shared-network"
          className="text-[13px] text-muted underline underline-offset-4 hover:text-ink"
        >
          {t("sharedNetwork")}
        </Link>
      )}
    </div>
  );
}

export function QuotaCounter() {
  const { quota } = useVisitor();
  if (quota === null) {
    return null;
  }
  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-2.5 sm:px-6">
      <QuotaLine quota={quota} />
    </div>
  );
}
