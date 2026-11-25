"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";

import { Link, usePathname } from "@/i18n/navigation";
import { PHONE_QUERY } from "@/lib/phone-mode";

import { AccountLinks } from "./account/account-menu";
import { HEADER_INPUT_ID, HOME_INPUT_ID } from "./analysis-field";
import { CloseIcon, MenuIcon } from "./icons";
import { LocaleSwitcher } from "./locale-switcher";
import { CompactQuota, QuotaLine } from "./quota-counter";
import { ThemeSwitcher } from "./theme-switcher";
import { useVisitor } from "./visitor-context";

export const PHONE_BAR_ID = "phone-bar";
export const PHONE_MENU_ID = "phone-menu";

function analysisInput(): HTMLElement | null {
  return document.getElementById(HOME_INPUT_ID) ?? document.getElementById(HEADER_INPUT_ID);
}

function MenuPanel() {
  const { quota } = useVisitor();
  return (
    <div
      id={PHONE_MENU_ID}
      data-phone-menu=""
      className="absolute inset-x-0 top-16 max-h-[calc(100dvh-4rem)] overflow-y-auto bg-page shadow-[0_1px_0_var(--line)]"
    >
      <div className="mx-auto flex max-w-[1180px] flex-col items-start gap-4 px-4 pt-3 pb-5 sm:px-6">
        {quota !== null && <QuotaLine quota={quota} tall />}
        <ThemeSwitcher />
        <LocaleSwitcher />
        <AccountLinks />
      </div>
    </div>
  );
}

export function PhoneBar() {
  const t = useTranslations("header");
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openedOn, setOpenedOn] = useState(pathname);
  const bar = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  if (open && openedOn !== pathname) {
    setOpen(false);
  }

  useEffect(() => {
    if (!open) {
      return;
    }
    const media = window.matchMedia(PHONE_QUERY);
    function closeOnDesk() {
      if (!media.matches) {
        setOpen(false);
      }
    }
    function closeOutside(event: PointerEvent) {
      if (bar.current !== null && event.target instanceof Node && !bar.current.contains(event.target)) {
        setOpen(false);
      }
    }
    media.addEventListener("change", closeOnDesk);
    document.addEventListener("pointerdown", closeOutside);
    return () => {
      media.removeEventListener("change", closeOnDesk);
      document.removeEventListener("pointerdown", closeOutside);
    };
  }, [open]);

  function toggle() {
    setOpenedOn(pathname);
    setOpen(!open);
  }

  function closeOnEscape(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    }
  }

  function closeWhenFocusLeaves(event: FocusEvent<HTMLDivElement>) {
    const next = event.relatedTarget;
    if (next instanceof Node && bar.current !== null && !bar.current.contains(next)) {
      setOpen(false);
    }
  }

  function goToField() {
    setOpen(false);
    const field = analysisInput();
    if (field === null) {
      return;
    }
    field.focus();
  }

  return (
    <div
      ref={bar}
      id={PHONE_BAR_ID}
      data-phone-bar=""
      data-header-stuck=""
      onKeyDown={closeOnEscape}
      onBlur={closeWhenFocusLeaves}
      className="fixed inset-x-0 top-0 z-30 h-16 bg-page shadow-[0_1px_0_var(--line)] desk:hidden"
    >
      <div className="mx-auto flex h-full max-w-[1180px] items-center gap-2 px-3 sm:gap-3 sm:px-6">
        <Link href="/" aria-label={t("home")} className="mr-auto flex min-h-11 shrink-0 items-center gap-2 rounded-md text-ink no-underline">
          <span aria-hidden="true" className="size-3 rounded-full bg-accent shadow-logo-glow" />
          <span className="font-condensed text-[22px] font-bold tracking-[0.08em]">{t("brand")}</span>
        </Link>
        <CompactQuota />
        <button
          type="button"
          onClick={goToField}
          data-new-analysis=""
          className="min-h-11 max-w-[7.5rem] min-w-0 cursor-pointer rounded-[10px] bg-accent px-3 font-condensed text-[15px] leading-[1.05] font-bold tracking-[0.06em] text-on-accent uppercase hover:bg-accent-hover min-[400px]:max-w-none"
        >
          {t("newAnalysis")}
        </button>
        <button
          ref={button}
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={PHONE_MENU_ID}
          data-menu-button=""
          className="flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-[10px] border-[1.5px] border-btn-border px-2.5 font-semibold text-ink hover:bg-row-hover"
        >
          {open && <CloseIcon className="size-5 stroke-current" />}
          {!open && <MenuIcon className="size-5 stroke-current" />}
          <span className="max-[359px]:sr-only">{t("menu")}</span>
        </button>
      </div>
      {open && <MenuPanel />}
    </div>
  );
}
