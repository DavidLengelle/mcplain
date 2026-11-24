"use client";

import { useTranslations } from "next-intl";

import { AccountCard, LINK_CLASS } from "@/components/account/form-parts";
import { Link } from "@/i18n/navigation";
import { authClient } from "@/lib/auth-client";
import { hasTwoFactor, isAdminRole } from "@/lib/two-factor";

import { AccountsSection } from "./accounts-section";
import { Dashboard } from "./dashboard";

export function AdminPanel() {
  const t = useTranslations("admin");
  const session = authClient.useSession();

  if (session.isPending) {
    return (
      <AccountCard title={t("title")}>
        <p>{t("loading")}</p>
      </AccountCard>
    );
  }
  const user = session.data?.user;
  if (!user) {
    return (
      <AccountCard title={t("title")}>
        <p>{t("signedOut")}</p>
        <p>
          <Link href="/account/sign-in" className={LINK_CLASS}>
            {t("signInLink")}
          </Link>
        </p>
      </AccountCard>
    );
  }
  if (!isAdminRole(user)) {
    return (
      <AccountCard title={t("title")}>
        <p data-testid="admin-not-admin">{t("notAdmin")}</p>
      </AccountCard>
    );
  }
  if (!hasTwoFactor(user)) {
    return (
      <AccountCard title={t("title")}>
        <p data-testid="admin-needs-two-factor" className="font-semibold text-ink">
          {t("needTwoFactor")}
        </p>
        <p>
          <Link href="/account#security" className={LINK_CLASS}>
            {t("securityLink")}
          </Link>
        </p>
      </AccountCard>
    );
  }
  return (
    <div className="mx-auto flex w-full max-w-[960px] flex-col gap-6">
      <h1 className="font-condensed text-[38px] leading-tight font-bold sm:text-[44px]">{t("title")}</h1>
      <Dashboard />
      <AccountsSection ownId={user.id} />
    </div>
  );
}
