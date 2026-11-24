"use client";

import { typedBackupCode, typedCode } from "@/lib/two-factor";

import { INPUT_CLASS } from "./form-parts";

type CodeFieldProps = {
  id: string;
  label: string;
  help: string;
  value: string;
  onChange: (value: string) => void;
  kind: "totp" | "backup";
};

export function CodeField({ id, label, help, value, onChange, kind }: CodeFieldProps) {
  const helpId = `${id}-help`;
  let inputMode: "numeric" | "text" = "text";
  let autoComplete = "off";
  let pattern: string | undefined;
  let clean = typedBackupCode;
  if (kind === "totp") {
    inputMode = "numeric";
    autoComplete = "one-time-code";
    pattern = "[0-9]{6}";
    clean = typedCode;
  }
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[15px] font-semibold text-ink">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type="text"
        value={value}
        required
        inputMode={inputMode}
        autoComplete={autoComplete}
        pattern={pattern}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        aria-describedby={helpId}
        onChange={(event) => onChange(clean(event.target.value))}
        className={`${INPUT_CLASS} font-mono tracking-[0.2em]`}
      />
      <p id={helpId} className="text-sm text-muted">
        {help}
      </p>
    </div>
  );
}
