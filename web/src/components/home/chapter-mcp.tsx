import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { GUIDE_SOURCES } from "@/lib/constants";
import { cn } from "@/lib/utils";

import { DocumentIcon, LampIcon, MailIcon, PlugIcon } from "../icons";
import { Bold, Chapter, ChapterHeading, linkTo, NOTE } from "./guide-parts";

const PARAGRAPH = "mt-3 max-w-[60ch] text-[19px] leading-[1.6] text-ink2";
const ICON = "mx-auto mb-1.5 block size-[22px] stroke-accent";

function Connector() {
  return <span className="h-[22px] w-0.5 bg-muted" />;
}

function Target({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="rounded-xl bg-panel2 px-1.5 py-3 text-center text-sm font-semibold">
      {icon}
      {label}
    </div>
  );
}

function McpDiagram() {
  const t = useTranslations("home.chapters.mcp.diagram");

  return (
    <div
      aria-hidden="true"
      data-mcp-diagram=""
      className="flex max-w-[480px] min-w-0 flex-[1_1_340px] flex-col items-center rounded-[22px] bg-panel p-6"
    >
      <div className="w-full rounded-[14px] bg-panel2 px-[18px] py-4 text-center shadow-sel-ring">
        <p className="font-condensed text-xl font-bold tracking-[0.08em]">{t("assistant")}</p>
        <p className="mt-0.5 text-sm text-muted">{t("assistantNote")}</p>
      </div>
      <Connector />
      <p className="flex items-center gap-2 rounded-full bg-accent px-3.5 py-1.5 font-condensed text-base font-bold tracking-[0.08em] text-on-accent">
        <PlugIcon className="size-[18px] stroke-on-accent" />
        {t("plugs")}
      </p>
      <Connector />
      <div className="grid w-full grid-cols-3 gap-2">
        <Target icon={<DocumentIcon className={ICON} />} label={t("files")} />
        <Target icon={<LampIcon lamp="internet" className={ICON} />} label={t("internet")} />
        <Target icon={<MailIcon className={ICON} />} label={t("mail")} />
      </div>
    </div>
  );
}

export function ChapterMcp() {
  const t = useTranslations("home.chapters.mcp");

  return (
    <Chapter id="mcp" className="flex flex-wrap items-center gap-x-12 gap-y-8">
      <div className="min-w-0 flex-[999_1_440px]">
        <ChapterHeading id="mcp" />
        <p className="mt-4 max-w-[60ch] text-[19px] leading-[1.6]">{t.rich("p1", { b: Bold })}</p>
        <p className={PARAGRAPH}>{t("p2")}</p>
        <p className={PARAGRAPH}>{t.rich("p3", { b: Bold })}</p>
        <p className={cn(NOTE, "mt-4")}>{t.rich("source", { link: linkTo(GUIDE_SOURCES.mcpIntro) })}</p>
      </div>
      <McpDiagram />
    </Chapter>
  );
}
