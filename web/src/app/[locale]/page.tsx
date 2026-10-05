import { useTranslations } from "next-intl";

export default function HomePage() {
  const t = useTranslations("home");

  return <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("tagline")}</h1>;
}
