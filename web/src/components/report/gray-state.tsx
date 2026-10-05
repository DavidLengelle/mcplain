import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import { VerdictPanel } from "./verdict-panel";

export function GrayState({ kind }: { kind: "unverified" | "timeout" }) {
  const t = useTranslations("grayStates");

  return (
    <div className="flex flex-col gap-4">
      <VerdictPanel color="gray">
        <h3 className="text-xl font-bold">{t(`${kind}.title`)}</h3>
        <p>{t(`${kind}.body`)}</p>
      </VerdictPanel>
      <p>
        <Link href="/" className="font-semibold underline underline-offset-4">
          {t("home")}
        </Link>
      </p>
    </div>
  );
}
