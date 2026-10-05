import { TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function EngineNotice() {
  const t = useTranslations("engineNotice");

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pt-4">
      <Alert>
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>{t("title")}</AlertTitle>
        <AlertDescription>{t("body")}</AlertDescription>
      </Alert>
    </div>
  );
}
