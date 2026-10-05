import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

export default function NotFoundPage() {
  const t = useTranslations("notFound");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p>{t("body")}</p>
      <p>
        <Link href="/" className="underline underline-offset-4">
          {t("home")}
        </Link>
      </p>
    </div>
  );
}
