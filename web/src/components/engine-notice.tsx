import { useTranslations } from "next-intl";

export function EngineNotice() {
  const t = useTranslations("engineNotice");

  return (
    <div className="mx-auto w-full max-w-[1180px] px-4 pt-4 sm:px-6">
      <div role="note" className="rounded-2xl bg-warn-note px-5 py-4 text-ink shadow-[inset_0_0_0_1.5px_var(--warn)]">
        <p className="font-condensed text-lg font-bold tracking-[0.06em] text-warn-text">{t("title")}</p>
        <p className="mt-1">{t("body")}</p>
      </div>
    </div>
  );
}
