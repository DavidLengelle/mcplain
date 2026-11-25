"use client";

import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { authClient } from "@/lib/auth-client";

const ITEM_CLASS = "flex min-h-11 w-full items-center rounded-md px-3 text-left text-ink no-underline hover:bg-row-hover hover:inset-ring-2 hover:inset-ring-muted";
const OUTLINE_CLASS =
  "flex min-h-11 items-center rounded-[10px] border-[1.5px] border-btn-border px-3.5 font-semibold text-ink no-underline hover:bg-row-hover";

function useSignOut(): () => Promise<void> {
  const router = useRouter();
  return async () => {
    await authClient.signOut();
    router.push("/");
  };
}

export function AccountMenu() {
  const t = useTranslations("account.menu");
  const session = authClient.useSession();
  const signOut = useSignOut();

  if (!session.data?.user) {
    return (
      <Link href="/account/sign-in" data-testid="header-sign-in" className={OUTLINE_CLASS}>
        {t("signIn")}
      </Link>
    );
  }

  return (
    <details className="relative" data-testid="header-account">
      <summary className={`${OUTLINE_CLASS} cursor-pointer list-none`}>{t("account")}</summary>
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

export function AccountLinks() {
  const t = useTranslations("account.menu");
  const session = authClient.useSession();
  const signOut = useSignOut();

  if (!session.data?.user) {
    return (
      <Link href="/account/sign-in" data-menu-account="sign-in" className={OUTLINE_CLASS}>
        {t("signIn")}
      </Link>
    );
  }

  return (
    <div className="flex flex-wrap gap-2.5" data-menu-account="signed-in">
      <Link href="/account" className={OUTLINE_CLASS}>
        {t("account")}
      </Link>
      <button type="button" onClick={signOut} className={`${OUTLINE_CLASS} cursor-pointer bg-transparent`}>
        {t("signOut")}
      </button>
    </div>
  );
}
