"use client";

import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { authClient } from "@/lib/auth-client";

const ITEM_CLASS = "flex min-h-11 w-full items-center rounded-md px-3 text-left text-ink no-underline hover:bg-row-hover";

export function AccountMenu() {
  const t = useTranslations("account.menu");
  const router = useRouter();
  const session = authClient.useSession();

  async function signOut() {
    await authClient.signOut();
    router.push("/");
  }

  if (!session.data?.user) {
    return (
      <Link
        href="/account/sign-in"
        data-testid="header-sign-in"
        className="flex min-h-11 items-center rounded-[10px] border-[1.5px] border-btn-border px-3.5 font-semibold text-ink no-underline hover:bg-row-hover"
      >
        {t("signIn")}
      </Link>
    );
  }

  return (
    <details className="relative" data-testid="header-account">
      <summary
        aria-label={t("menuLabel")}
        className="flex min-h-11 cursor-pointer list-none items-center rounded-[10px] border-[1.5px] border-btn-border px-3.5 font-semibold text-ink hover:bg-row-hover"
      >
        {t("account")}
      </summary>
      <div className="absolute right-0 z-30 mt-2 flex w-56 flex-col gap-1 rounded-[14px] bg-panel2 p-2 shadow-[0_0_0_1px_var(--line)]">
        <Link href="/account" className={ITEM_CLASS}>
          {t("account")}
        </Link>
        <button type="button" onClick={signOut} className={`${ITEM_CLASS} cursor-pointer`}>
          {t("signOut")}
        </button>
      </div>
    </details>
  );
}
