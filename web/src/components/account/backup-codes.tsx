"use client";

import { useTranslations } from "next-intl";

import { RawText } from "@/components/raw-text";
import { printInLight } from "@/lib/print";

import { BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from "./form-parts";

export function BackupCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const t = useTranslations("account.security");
  return (
    <div data-print-area data-testid="backup-codes" className="flex flex-col gap-3 rounded-[14px] bg-panel2 p-5 text-ink">
      <h3 className="font-condensed text-[24px] font-bold">{t("codesTitle")}</h3>
      <p>{t("codesIntro")}</p>
      <p className="font-semibold">{t("codesOnce")}</p>
      <ol className="grid grid-cols-2 gap-2 font-mono text-[17px]">
        {codes.map((code) => (
          <li key={code} data-testid="backup-code" className="rounded-md border-[1.5px] border-btn-border px-3 py-2">
            <RawText value={code} />
          </li>
        ))}
      </ol>
      <div data-print-hide className="flex flex-wrap gap-3">
        <button type="button" onClick={printInLight} className={SECONDARY_BUTTON_CLASS}>
          {t("print")}
        </button>
        <button type="button" onClick={onDone} className={BUTTON_CLASS}>
          {t("codesDone")}
        </button>
      </div>
    </div>
  );
}
