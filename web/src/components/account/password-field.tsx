"use client";

import { useTranslations } from "next-intl";
import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import { INPUT_CLASS } from "./form-parts";

export type PasswordAutoComplete = "new-password" | "current-password";

type PasswordFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: PasswordAutoComplete;
  resetCount: number;
  help?: string;
  minLength?: number;
  maxLength?: number;
};

type Selection = { start: number | null; end: number | null };

function stopEnter(event: KeyboardEvent<HTMLInputElement>) {
  if (event.key === "Enter") {
    event.preventDefault();
  }
}

export function PasswordField({ id, label, value, onChange, autoComplete, resetCount, help, minLength, maxLength }: PasswordFieldProps) {
  const t = useTranslations("account.common");
  const input = useRef<HTMLInputElement>(null);
  const selection = useRef<Selection | null>(null);
  const [shown, setShown] = useState(false);
  const [seenReset, setSeenReset] = useState(resetCount);
  if (seenReset !== resetCount) {
    setSeenReset(resetCount);
    setShown(false);
  }

  useLayoutEffect(() => {
    const element = input.current;
    const kept = selection.current;
    selection.current = null;
    if (element === null || kept === null || kept.start === null || kept.end === null) {
      return;
    }
    element.setSelectionRange(kept.start, kept.end);
  }, [shown]);

  function toggle(checked: boolean) {
    const element = input.current;
    if (element !== null) {
      selection.current = { start: element.selectionStart, end: element.selectionEnd };
    }
    setShown(checked);
  }

  const helpId = `${id}-help`;
  const toggleId = `${id}-show`;
  let described: string | undefined = undefined;
  if (help !== undefined) {
    described = helpId;
  }
  let type = "password";
  if (shown) {
    type = "text";
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[15px] font-semibold text-ink">
        {label}
      </label>
      <input
        ref={input}
        id={id}
        name={id}
        type={type}
        value={value}
        required
        minLength={minLength}
        maxLength={maxLength}
        autoComplete={autoComplete}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        aria-describedby={described}
        data-password-field=""
        onChange={(event) => onChange(event.target.value)}
        className={INPUT_CLASS}
      />
      {help !== undefined && (
        <p id={helpId} className="text-sm text-muted">
          {help}
        </p>
      )}
      <div className="flex min-h-11 items-center gap-2.5">
        <input
          id={toggleId}
          type="checkbox"
          checked={shown}
          aria-controls={id}
          onChange={(event) => toggle(event.target.checked)}
          onKeyDown={stopEnter}
          className="size-5 shrink-0 cursor-pointer accent-accent"
        />
        <label htmlFor={toggleId} className="cursor-pointer text-[15px] text-ink2">
          {t("showPassword")}
        </label>
      </div>
    </div>
  );
}
