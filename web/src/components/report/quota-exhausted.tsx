"use client";

import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { nextMidnightUtc, type QuotaInfo } from "@/lib/quota";

import { useResetTime } from "../quota-counter";

const BUTTON_CLASS =
  "inline-flex min-h-11 items-center rounded-[10px] bg-accent px-5 font-condensed text-lg font-bold tracking-[0.06em] text-on-accent no-underline hover:bg-accent-hover";

export function QuotaExhausted({ quota }: { quota: QuotaInfo | null }) {
  const t = useTranslations("quota.exhausted");
  const resetTime = useResetTime();
  const time = resetTime(quota?.resetsAt ?? nextMidnightUtc(new Date()));
  const account = quota?.kind === "account";

  return (
    <section
      data-testid="quota-exhausted"
      aria-labelledby="quota-exhausted-heading"
      className="flex flex-col gap-4 rounded-[22px] bg-panel px-6 py-7 sm:px-8"
    >
      <h1 id="quota-exhausted-heading" className="font-condensed text-[32px] leading-tight font-bold tracking-[0.04em]">
        {t("title")}
      </h1>
      {account && <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">{t("account", { limit: quota?.limit ?? 0, time })}</p>}
      {!account && (
        <>
          <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">{t("anonymous", { time })}</p>
          <p className="max-w-[60ch] text-lg leading-[1.55] text-ink2">{t("sharedNetwork")}</p>
          <p>
            <Link href="/account/sign-up" data-testid="quota-create-account" className={BUTTON_CLASS}>
              {t("createAccount")}
            </Link>
          </p>
        </>
      )}
      <p className="max-w-[60ch] text-lg font-semibold text-ink">{t("cacheOpen")}</p>
    </section>
  );
}
